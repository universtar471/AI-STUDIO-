import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from services.core.domain import ImageProvider, RenderRequest
from services.providers.comfyui.config import ComfyUIConfig, load_config
from services.providers.comfyui.manifest import Manifest, inject, load_workflow
from services.providers.comfyui.provider import ComfyUIProvider

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.mark.parametrize('location', ['running', 'pending', 'other', 'offline', 'post_failure'])
def test_remote_cancel(location):
    async def scenario():
        fake = Fake()
        fake.hold = True
        writes = []
        async def endpoint(req):
            if req.url.path == '/queue' and req.method == 'GET':
                if location == 'offline':
                    raise httpx.ReadTimeout('private details')
                return httpx.Response(200, json={
                    'queue_running': [[0, '1' if location in ('running', 'post_failure') else 'other']],
                    'queue_pending': [[1, '1']] if location == 'pending' else []})
            if req.method == 'POST' and req.url.path in ('/interrupt', '/queue'):
                writes.append((req.url.path, json.loads(req.content)))
                if location == 'post_failure':
                    raise httpx.ConnectError('private details')
                return httpx.Response(200, json={})
            return await fake.http(req)
        p = ComfyUIProvider(Images(), config=config(), transport=httpx.MockTransport(endpoint), ws_connect=fake.websocket)
        job = await p.submit(request())
        for _ in range(100):
            if (await p.poll(job.provider_job_id)).progress == .5:
                break
            await asyncio.sleep(.001)
        assert fake.graphs
        await p.cancel(job.provider_job_id)
        await p.cancel(job.provider_job_id)
        assert (await p.poll(job.provider_job_id)).state == 'cancelled'
        expected = [('/interrupt', {})] if location in ('running', 'post_failure') else [('/queue', {'delete': ['1']})] if location == 'pending' else []
        assert writes == expected
        assert not fake.connected
    asyncio.run(scenario())


@pytest.mark.parametrize('failure', ['connect', 'connect_timeout', 'websocket'])
def test_execution_invalidates_health(failure):
    async def scenario():
        fake = Fake()
        async def endpoint(req):
            if req.url.path == '/upload/image' and failure != 'websocket':
                error = httpx.ConnectError if failure == 'connect' else httpx.ConnectTimeout
                raise error('private details')
            return await fake.http(req)
        @asynccontextmanager
        async def broken_ws(*args, **kwargs):
            raise OSError('private details')
            yield
        p = ComfyUIProvider(Images(), config=config(), transport=httpx.MockTransport(endpoint), ws_connect=broken_ws)
        assert (await p.health()).status == 'ok'
        assert (await finish(p, await p.submit(request()))).state == 'failed'
        assert (await p.health()).status == 'ok'
        assert fake.calls.count('/object_info') == 2
    asyncio.run(scenario())


@pytest.mark.parametrize('free,running,threshold,expected', [
    (1024, [], 6000, 'degraded'), (1024, [[0, 'other']], 6000, 'ok'),
    (6000, [], 6000, 'ok'), (1024, [], 512, 'ok'),
    (None, [], 6000, 'ok'), ('unknown', [], 6000, 'ok'), (-1, [], 6000, 'ok'),
])
def test_vram_preflight(free, running, threshold, expected):
    async def scenario():
        fake = Fake()
        async def endpoint(req):
            if req.url.path == '/system_stats':
                value = free * 1024 * 1024 if isinstance(free, int) else free
                return httpx.Response(404) if free is None else httpx.Response(200, json={'devices': [{'vram_free': value}]})
            if req.url.path == '/queue':
                return httpx.Response(200, json={'queue_running': running, 'queue_pending': []})
            return await fake.http(req)
        p = ComfyUIProvider(Images(), config=config(min_free_vram_mb=threshold), transport=httpx.MockTransport(endpoint))
        health = await p.health()
        assert health.status == expected
        if expected == 'degraded':
            assert '1024 MB' in health.detail and 'GPU' in health.detail
    asyncio.run(scenario())


@pytest.mark.parametrize('free_mb,torch_mb,expected', [
    (2000, 6000, 'ok'),
    (1000, 0, 'degraded'),
])
def test_vram_preflight_counts_reclaimable_torch_memory(free_mb, torch_mb, expected):
    async def scenario():
        fake = Fake()
        async def endpoint(req):
            if req.url.path == '/system_stats':
                return httpx.Response(200, json={'devices': [{
                    'vram_free': free_mb * 1024 * 1024,
                    'torch_vram_total': torch_mb * 1024 * 1024,
                }]})
            if req.url.path == '/queue':
                return httpx.Response(200, json={'queue_running': [], 'queue_pending': []})
            return await fake.http(req)
        p = ComfyUIProvider(Images(), config=config(), transport=httpx.MockTransport(endpoint))
        health = await p.health()
        assert health.status == expected
        if expected == 'degraded':
            assert f'{free_mb + torch_mb} MB' in health.detail
    asyncio.run(scenario())


class Images:
    def base_image(self, request):
        return 'base', b'base-bytes', 'image/png'

    def image(self, artifact_id):
        return artifact_id.encode(), 'image/png'


class Fake:
    def __init__(self, failures=()):
        self.failures = list(failures)
        self.graphs, self.uploads, self.calls = [], [], []
        self.events = asyncio.Queue()
        self.info = {'TestOnly': {}, 'TestLoader': {'input': {'required': {'model': [['dummy.bin']]}}}}
        self.connected = False
        self.hold = False

    async def http(self, request):
        path = request.url.path
        self.calls.append(path)
        if path == '/object_info':
            return httpx.Response(200, json=self.info)
        if path == '/system_stats':
            return httpx.Response(404)
        if path == '/queue':
            return httpx.Response(200, json={'queue_running': [], 'queue_pending': []})
        if path == '/upload/image':
            self.uploads.append(await request.aread())
            return httpx.Response(200, json={'name': f'{len(self.uploads)}.png', 'subfolder': 'studio', 'type': 'input'})
        if path == '/prompt':
            assert self.connected
            body = json.loads(request.content)
            assert body['client_id'] == self.client_id
            self.graphs.append(body['prompt'])
            pid = str(len(self.graphs))
            await self.events.put({'type': 'progress', 'data': {'prompt_id': 'other', 'value': 1, 'max': 1}})
            await self.events.put({'type': 'progress', 'data': {'prompt_id': pid, 'value': 1, 'max': 2}})
            failure = self.failures.pop(0) if self.failures else None
            if not self.hold:
                await self.events.put({'type': 'execution_error' if failure else 'executing', 'data': {'prompt_id': pid, 'node': None, 'exception_type': failure or ''}})
            return httpx.Response(200, json={'prompt_id': pid})
        if path.startswith('/history/'):
            return httpx.Response(200, json={path.rsplit('/', 1)[1]: {'outputs': {'9': {'images': [{'filename': 'out.png', 'subfolder': '', 'type': 'output'}]}}}})
        if path == '/view':
            assert request.url.params['filename'] == 'out.png'
            return httpx.Response(200, content=b'output-bytes', headers={'content-type': 'image/png'})
        raise AssertionError(path)

    @asynccontextmanager
    async def websocket(self, url, **kwargs):
        from urllib.parse import parse_qs, urlsplit
        self.client_id = parse_qs(urlsplit(url).query)['clientId'][0]
        self.connected = True
        try:
            yield self
        finally:
            self.connected = False

    async def recv(self):
        event = await self.events.get()
        await asyncio.sleep(0)
        return json.dumps(event)


def config(**kwargs):
    return ComfyUIConfig(manifest_dir=FIXTURES, workflow_dir=FIXTURES, manifest='manifest.json', **kwargs)


def request(**kwargs):
    return RenderRequest(project_id='p', mode='sketchup_render', source={'artifact_id': 'base'}, seed=42,
                         references=[{'artifact_id': 'decor', 'role': 'DECOR'}, {'artifact_id': 'style', 'role': 'STYLE_MASTER'}], **kwargs)


async def finish(provider, job):
    for _ in range(500):
        status = await provider.poll(job.provider_job_id)
        if status.state in ('succeeded', 'failed', 'cancelled'):
            return status
        await asyncio.sleep(.001)
    raise AssertionError('job did not finish')


def test_complete_flow_and_snapshot():
    async def scenario():
        fake = Fake()
        p = ComfyUIProvider(Images(), config=config(), transport=httpx.MockTransport(fake.http), ws_connect=fake.websocket)
        assert isinstance(p, ImageProvider)
        assert (await p.health()).status == 'ok'
        job = await p.submit(request(prompt={'raw_text': 'verbatim prompt'}))
        status = await finish(p, job)
        assert status.state == 'succeeded'
        graph = fake.graphs[0]['1']['inputs']
        assert {k: graph[k] for k in ('source', 'ref', 'text', 'edge', 'seed', 'steps', 'cfg')} == {
            'source': 'studio/1.png', 'ref': 'studio/2.png', 'text': 'verbatim prompt', 'edge': 1536, 'seed': 42, 'steps': 8, 'cfg': 2.0}
        assert graph['prefix'].startswith('studio-')
        assert graph['untouched'] == ['2', 0]
        assert b'base-bytes' in fake.uploads[0] and b'style' in fake.uploads[1]
        assert job.provider_request['prompt'] == 'verbatim prompt'
        assert job.provider_request['workflow'] == 'test-only'
        assert [i['artifact_id'] for i in job.provider_request['images']] == ['base', 'style']
        assert job.provider_request['images'][0]['sha256'] == hashlib.sha256(b'base-bytes').hexdigest()
        json.dumps(job.provider_request)
        assert status.metrics.extra['template_sha256'] == hashlib.sha256((FIXTURES / 'template.json').read_bytes()).hexdigest()
        assert status.metrics.extra['custom_nodes'] == {'TestOnly': 'test-1'}
        assert status.metrics.duration_s >= 0
        assert (await p.fetch_result(job.provider_job_id))[0].data == b'output-bytes'
        assert fake.calls[-2:] == ['/history/1', '/view']
    asyncio.run(scenario())


@pytest.mark.parametrize('failures,size,expected,attempts', [
    (['OutOfMemoryError'], None, 'succeeded', 2),
    (['CUDA out of memory', 'OutOfMemory'], None, 'failed', 2),
    (['OutOfMemory'], '1024', 'failed', 1),
    (['RuntimeError'], None, 'failed', 1),
])
def test_fallback(failures, size, expected, attempts):
    async def scenario():
        fake = Fake(failures)
        p = ComfyUIProvider(Images(), config=config(), transport=httpx.MockTransport(fake.http), ws_connect=fake.websocket)
        status = await finish(p, await p.submit(request(image_size=size)))
        assert status.state == expected
        assert len(fake.graphs) == attempts
        if attempts == 2:
            assert fake.graphs[1]['1']['inputs']['edge'] == 1024
            assert status.metrics.extra['vram_fallback'] is True
        if expected == 'failed':
            assert status.error.code == ('COMFYUI_EXECUTION_ERROR' if failures[0] == 'RuntimeError' else 'COMFYUI_OUT_OF_MEMORY')
    asyncio.run(scenario())


@pytest.mark.parametrize('missing', ['TestOnly', 'checkpoints/dummy.bin', 'offline', 'workflow'])
def test_health_unavailable(missing, tmp_path):
    async def scenario():
        fake = Fake()
        if missing == 'TestOnly':
            del fake.info['TestOnly']
        elif missing == 'checkpoints/dummy.bin':
            fake.info['TestLoader']['input']['required']['model'] = [[]]
        async def offline(req):
            raise httpx.ConnectError('offline')
        cfg = config() if missing != 'workflow' else ComfyUIConfig(manifest_dir=tmp_path, workflow_dir=tmp_path)
        p = ComfyUIProvider(Images(), config=cfg, transport=httpx.MockTransport(offline if missing == 'offline' else fake.http))
        health = await p.health()
        assert health.status == 'unavailable'
        assert ('chưa có workflow từ Đợt 0' if missing == 'workflow' else missing) in health.detail
    asyncio.run(scenario())


def test_injection_isolated_and_manifest_drives_presets():
    manifest, template, _ = load_workflow(config())
    original = json.dumps(template)
    manifest.presets['PREVIEW_FAST'] = manifest.presets['PREVIEW_FAST'].model_copy(update={'steps': 17, 'cfg': 3.5})
    graph = inject(template, manifest, source_image='base', reference_image=['ref'], prompt='text', seed=9, filename_prefix='test', preset='PREVIEW_FAST')
    assert graph['1']['inputs']['steps'] == 17 and graph['1']['inputs']['cfg'] == 3.5
    assert json.dumps(template) == original
    del template['1']['inputs']['text']
    with pytest.raises(ValueError, match='1.*text'):
        inject(template, manifest, source_image='base', reference_image=[], prompt='text', seed=9, filename_prefix='test', preset='PREVIEW_FAST')


def test_config_environment(monkeypatch, tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'url': 'http://localhost:9999', 'manifest_dir': str(tmp_path)}))
    monkeypatch.setenv('AI_STUDIO_COMFYUI_CONFIG', str(path))
    assert load_config().url == 'http://localhost:9999'


def test_default_config_is_independent_of_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv('AI_STUDIO_COMFYUI_CONFIG', raising=False)
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    root = Path(__file__).resolve().parents[3]
    assert cfg.manifest_dir == root / 'workflows/manifests'
    assert cfg.workflow_dir == root / 'workflows/comfyui'
    assert cfg.manifest == 'flux2_klein_4b_preview.json'
    assert cfg.models_dir is None
    assert cfg.timeout_s == 600
    load_workflow(cfg)


@pytest.mark.parametrize('ttl', [30, 12, 0])
def test_health_cache_expiry(monkeypatch, ttl):
    async def scenario():
        now = [100.0]
        monkeypatch.setattr('services.providers.comfyui.provider.time.monotonic', lambda: now[0])
        fake = Fake()
        cfg = config() if ttl == 30 else config(health_cache_ttl_s=ttl)
        p = ComfyUIProvider(Images(), config=cfg, transport=httpx.MockTransport(fake.http))
        assert (await p.health()).status == 'ok'
        assert (await p.health()).status == 'ok'
        assert fake.calls.count('/object_info') == (2 if ttl == 0 else 1)
        now[0] += ttl
        await p.health()
        assert fake.calls.count('/object_info') == (3 if ttl == 0 else 2)
    asyncio.run(scenario())


def test_connection_failure_cache_recovers_after_five_seconds(monkeypatch):
    async def scenario():
        now = [100.0]
        monkeypatch.setattr('services.providers.comfyui.provider.time.monotonic', lambda: now[0])
        calls = []
        fake = Fake()
        async def endpoint(req):
            calls.append(req.url.path)
            if len(calls) == 1:
                raise httpx.ConnectError('offline')
            return await fake.http(req)
        p = ComfyUIProvider(Images(), config=config(), transport=httpx.MockTransport(endpoint))
        assert (await p.health()).status == 'unavailable'
        now[0] += 4.9
        assert (await p.health()).status == 'unavailable'
        assert len(calls) == 1
        now[0] += .1
        assert (await p.health()).status == 'ok'
        assert calls.count('/object_info') == 2
    asyncio.run(scenario())


def test_timeout_and_cancel():
    async def scenario():
        fake = Fake()
        fake.hold = True
        p = ComfyUIProvider(Images(), config=config(timeout_s=.05), transport=httpx.MockTransport(fake.http), ws_connect=fake.websocket)
        job = await p.submit(request())
        status = await finish(p, job)
        assert status.error.code == 'COMFYUI_TIMEOUT'
        job = await p.submit(request())
        await p.cancel(job.provider_job_id)
        assert (await p.poll(job.provider_job_id)).state == 'cancelled'
        with pytest.raises(ValueError):
            await p.fetch_result(job.provider_job_id)
    asyncio.run(scenario())


def test_disk_models_hash_snapshot_and_changed_preset(tmp_path):
    async def scenario():
        model_dir = tmp_path / 'models'
        (model_dir / 'checkpoints').mkdir(parents=True)
        model_path = model_dir / 'checkpoints/dummy.bin'
        model_path.write_bytes(b'checkpoint')
        checksum = hashlib.sha256(b'checkpoint').hexdigest()
        manifest = json.loads((FIXTURES / 'manifest.json').read_text())
        manifest['models'][0]['sha256'] = checksum
        manifest['presets']['PREVIEW_QUALITY'].update(steps=23, cfg=4.5)
        (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
        cfg = ComfyUIConfig(manifest_dir=tmp_path, workflow_dir=FIXTURES, manifest='manifest.json', models_dir=model_dir, health_cache_ttl_s=0)
        fake = Fake()
        p = ComfyUIProvider(Images(), config=cfg, transport=httpx.MockTransport(fake.http), ws_connect=fake.websocket)
        assert (await p.health()).status == 'ok'
        job = await p.submit(request())
        status = await finish(p, job)
        assert fake.graphs[0]['1']['inputs']['steps'] == 23
        assert fake.graphs[0]['1']['inputs']['cfg'] == 4.5
        assert status.metrics.extra['checkpoint_sha256'] == {'checkpoints/dummy.bin': checksum}
        assert 'decor' in job.provider_request['prompt']
        model_path.write_bytes(b'changed')
        assert 'checksum mismatch: checkpoints/dummy.bin' in (await p.health()).detail
        model_path.unlink()
        assert 'Missing model: checkpoints/dummy.bin' in (await p.health()).detail
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['path', 'slots', 'overlap', 'preset'])
def test_invalid_manifest(change):
    data = json.loads((FIXTURES / 'manifest.json').read_text())
    if change == 'path':
        data['models'][0]['path'] = '../outside.bin'
    elif change == 'slots':
        data['max_reference_images'] = 2
    elif change == 'overlap':
        data['bindings']['seed'] = data['bindings']['prompt']
    else:
        data['presets']['PREVIEW_FAST']['long_edge'] = 999
    with pytest.raises(ValueError):
        Manifest.model_validate(data)


def test_missing_template_and_node(tmp_path):
    (tmp_path / 'manifest.json').write_bytes((FIXTURES / 'manifest.json').read_bytes())
    cfg = ComfyUIConfig(manifest_dir=tmp_path, workflow_dir=tmp_path, manifest='manifest.json')
    with pytest.raises(FileNotFoundError, match='chưa có workflow từ Đợt 0'):
        load_workflow(cfg)
    template = json.loads((FIXTURES / 'template.json').read_text())
    del template['1']
    (tmp_path / 'template.json').write_text(json.dumps(template))
    with pytest.raises(ValueError, match='1.source'):
        load_workflow(cfg)


def test_progress_is_visible_and_other_jobs_are_ignored():
    async def scenario():
        fake = Fake()
        fake.hold = True
        p = ComfyUIProvider(Images(), config=config(), transport=httpx.MockTransport(fake.http), ws_connect=fake.websocket)
        job = await p.submit(request())
        for _ in range(100):
            status = await p.poll(job.provider_job_id)
            if status.progress == .5:
                break
            await asyncio.sleep(.001)
        assert status.state == 'running' and status.progress == .5
        await p.cancel(job.provider_job_id)
        assert not fake.connected
    asyncio.run(scenario())


def test_unused_reference_slots_reuse_the_base_upload():
    # A template default filename would be a stale or missing image in ComfyUI.
    async def scenario():
        fake = Fake()
        p = ComfyUIProvider(Images(), config=config(), transport=httpx.MockTransport(fake.http), ws_connect=fake.websocket)
        job = await p.submit(RenderRequest(project_id='p', mode='sketchup_render', source={'artifact_id': 'base'}, prompt={'raw_text': 'x'}))
        assert (await finish(p, job)).state == 'succeeded'
        graph = fake.graphs[0]['1']['inputs']
        assert graph['ref'] == graph['source'] == 'studio/1.png'
        assert len(fake.uploads) == 1
    asyncio.run(scenario())
