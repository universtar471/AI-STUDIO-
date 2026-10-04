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
        cfg = ComfyUIConfig(manifest_dir=tmp_path, workflow_dir=FIXTURES, manifest='manifest.json', models_dir=model_dir)
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
