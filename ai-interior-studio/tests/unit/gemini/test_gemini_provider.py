import asyncio
from datetime import date
import json
from types import SimpleNamespace

import pytest

from services.core.domain import JobState, Project, ReferenceRole as R, ReferenceSlot, RenderRequest
from services.core.orchestration import JobManager
from services.core.storage import ArtifactStore, Database, DataRoot
from services.providers.gemini import GeminiConfig, GeminiImageProvider, StorageImageSource, load_config
from services.providers.mock import MockProvider

FAKE_KEY = 'AIza' + 'UnitTestKey' * 3 + 'xx'
OUT_PNG = b'\x89PNG\r\n\x1a\nGEMINI-OUT'


class FakeModels:
    def __init__(self, behaviour):
        self.calls, self.behaviour = [], list(behaviour)

    async def generate_content(self, *, model, contents, config):
        self.calls.append({'model': model, 'contents': contents, 'config': config})
        action = self.behaviour.pop(0) if self.behaviour else 'ok'
        if action == 'hang':
            await asyncio.sleep(10)
        if isinstance(action, Exception):
            raise action
        part = SimpleNamespace(inline_data=SimpleNamespace(data=OUT_PNG, mime_type='image/png'))
        return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))],
                               usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=1290, total_token_count=1300))


class FakeClient:
    def __init__(self, *behaviour):
        self.models = FakeModels(behaviour)
        self.aio = SimpleNamespace(models=self.models)
        self.keys = []

    def factory(self, key):
        self.keys.append(key)
        return self


class Env:
    def __init__(self, tmp_path):
        self.root = DataRoot(tmp_path / 'data')
        self.db = Database(self.root.db_path)
        self.store = ArtifactStore(self.root)
        self.project = self.db.projects.add(Project(name='P'))

    def image(self, name: str) -> str:
        artifact = self.store.put_bytes(self.project.id, f'image-{name}'.encode(), kind='reference', media_type='image/png')
        self.db.artifacts.add(artifact)
        return artifact.id

    def provider(self, client, *, key=FAKE_KEY, **config):
        return GeminiImageProvider(StorageImageSource(self.db, self.store), config=GeminiConfig(**config),
                                   api_key=lambda: key, client_factory=client.factory)

    def request(self, **kw):
        return RenderRequest(project_id=self.project.id, mode='sketchup_render',
                             source={'artifact_id': kw.pop('base', None) or self.image('base')}, **kw)


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    yield e
    e.db.close()


async def finish(provider, job, timeout=3):
    async with asyncio.timeout(timeout):
        while (status := await provider.poll(job.provider_job_id)).state in ('queued', 'running'):
            await asyncio.sleep(.005)
    return status


def test_six_images_keep_order_and_roles(env):
    async def run():
        base = env.image('base')
        ids = {role: env.image(role) for role in ('decor', 'floor', 'style', 'wall', 'approved')}
        refs = [ReferenceSlot(artifact_id=ids['decor'], role=R.DECOR), ReferenceSlot(artifact_id=ids['floor'], role=R.FLOOR),
                ReferenceSlot(artifact_id=ids['style'], role=R.STYLE_MASTER), ReferenceSlot(artifact_id=ids['wall'], role=R.WALL),
                ReferenceSlot(artifact_id=ids['approved'], role=R.APPROVED_VIEW)]
        client = FakeClient()
        provider = env.provider(client)
        job = await provider.submit(env.request(base=base, references=refs, prompt={'style': 'Japandi'}))
        status = await finish(provider, job)
        assert status.state == 'succeeded'

        call = client.models.calls[0]
        sent = [part.inline_data.data for part in call['contents'][:-1]]
        assert sent == [b'image-base', b'image-style', b'image-approved', b'image-floor', b'image-wall', b'image-decor']
        prompt = call['contents'][-1]
        expected = ['the base view', 'the master style', 'an approved view', 'floor reference', 'wall reference', 'decor reference']
        for index, start in enumerate(expected, 1):
            assert f'Image {index}: {start}' in prompt
        assert prompt.index('Image 1:') < prompt.index('Image 6:')
        record = job.provider_request
        assert [i['role'] for i in record['images']] == ['BASE_PLAN', 'STYLE_MASTER', 'APPROVED_VIEW', 'FLOOR', 'WALL', 'DECOR']
        assert call['model'] == 'gemini-3.1-flash-image'
        assert call['config'].image_config.image_size == '1K'
        assert call['config'].image_config.aspect_ratio == '16:9'
        outputs = await provider.fetch_result(job.provider_job_id)
        assert outputs[0].data == OUT_PNG
        assert status.metrics.cost_estimate == 0.067
        assert status.metrics.extra['usage']['total_token_count'] == 1300
    asyncio.run(run())


def test_model_and_limits_come_from_config(env, tmp_path):
    path = tmp_path / 'gemini.json'
    path.write_text(json.dumps({'model': 'some-future-image-model', 'max_reference_images': 3}), encoding='utf-8')
    config = load_config(path)
    provider = GeminiImageProvider(StorageImageSource(env.db, env.store), config=config, api_key=lambda: FAKE_KEY,
                                   client_factory=FakeClient().factory)
    assert provider.capabilities.max_reference_images == 2
    assert load_config().model == 'gemini-3.1-flash-image'

    async def run():
        refs = [ReferenceSlot(artifact_id=env.image(str(i)), role=role) for i, role in enumerate([R.DECOR, R.STYLE_MASTER, R.FLOOR, R.WALL])]
        job = await provider.submit(env.request(references=refs))
        record = job.provider_request
        assert record['model'] == 'some-future-image-model'
        assert [i['role'] for i in record['images']] == ['BASE_PLAN', 'STYLE_MASTER', 'FLOOR']
        assert len(record['dropped_references']) == 2
        assert 'could not be attached' in record['prompt']
    asyncio.run(run())


def test_4k_needs_confirmation(env):
    async def run():
        provider = env.provider(FakeClient())
        result = await provider.validate(env.request(image_size='4K'))
        assert not result.ok and result.errors[0].code == 'HIGH_COST_NOT_CONFIRMED'
        assert (await provider.validate(env.request(image_size='4K', confirm_high_cost=True))).ok
        job = await provider.submit(env.request(image_size='4K', confirm_high_cost=True))
        assert (await finish(provider, job)).metrics.cost_estimate == 0.151
        with pytest.raises(ValueError, match='HIGH_COST_NOT_CONFIRMED'):
            await provider.submit(env.request(image_size='4K'))
    asyncio.run(run())


def test_daily_limit_fails_job_with_clear_code(env):
    async def run():
        provider = env.provider(FakeClient(), daily_call_limit=1)
        manager = JobManager(env.db, env.root, [provider], poll_interval=.001, timeout=5)
        await manager.start()
        try:
            first = await manager.submit(env.request(provider_policy='cloud_only', prompt={'raw_text': 'a'}))
            second = await manager.submit(env.request(provider_policy='cloud_only', prompt={'raw_text': 'b'}))
            async with asyncio.timeout(3):
                while env.db.jobs.get(second.id).state not in ('FAILED', 'REVIEW'):
                    await asyncio.sleep(.005)
            assert env.db.jobs.get(first.id).state == JobState.REVIEW
            failed = env.db.jobs.get(second.id)
            assert failed.state == JobState.FAILED
            assert failed.error.code == 'GEMINI_DAILY_LIMIT'
            assert failed.error.retryable is False
        finally:
            await manager.stop()
    asyncio.run(run())


def test_without_key_gemini_is_unavailable_and_mock_still_runs(env):
    async def run():
        client = FakeClient()
        gemini = env.provider(client, key=None)
        assert (await gemini.health()).status == 'unavailable'
        manager = JobManager(env.db, env.root, [gemini, MockProvider(delay=0)], poll_interval=.001)
        await manager.start()
        try:
            job = await manager.submit(env.request(prompt={'raw_text': 'x'}))
            async with asyncio.timeout(3):
                while env.db.jobs.get(job.id).state != JobState.REVIEW:
                    await asyncio.sleep(.005)
            assert env.db.jobs.get(job.id).provider_id == 'mock'
            assert client.models.calls == []
        finally:
            await manager.stop()
    asyncio.run(run())


def test_timeout_retries_and_same_request_is_not_paid_twice(env):
    async def run():
        client = FakeClient('hang', 'ok')
        provider = env.provider(client, timeout_s=.05, max_attempts=2)
        request = env.request(prompt={'raw_text': 'same'})
        job = await provider.submit(request)
        again = await provider.submit(request)
        assert again.provider_job_id == job.provider_job_id and again.provider_request['reused_run']
        status = await finish(provider, job)
        assert status.state == 'succeeded'
        assert status.metrics.extra['attempts'] == 2
        assert len(client.models.calls) == 2
        assert provider.usage.used() == 2

        gave_up = env.provider(FakeClient('hang', 'hang'), timeout_s=.02, max_attempts=2)
        status = await finish(gave_up, await gave_up.submit(request))
        assert status.error.code == 'GEMINI_TIMEOUT'
    asyncio.run(run())


def test_key_never_leaks(env):
    async def run():
        client = FakeClient(RuntimeError(f'401 for key={FAKE_KEY}'))
        provider = env.provider(client)
        job = await provider.submit(env.request(prompt={'raw_text': 'x'}))
        status = await finish(provider, job)
        assert status.error.code == 'GEMINI_API_ERROR'
        assert FAKE_KEY not in status.model_dump_json()
        assert FAKE_KEY not in json.dumps(job.provider_request)
        assert b'image-' not in json.dumps(job.provider_request).encode()
        assert client.keys == [FAKE_KEY]
    asyncio.run(run())


def test_no_image_in_response(env):
    client = FakeClient()

    async def no_image(**kwargs):
        return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(inline_data=None, text='refused')]))])
    client.models.generate_content = no_image

    async def run():
        provider = env.provider(client)
        status = await finish(provider, await provider.submit(env.request(prompt={'raw_text': 'x'})))
        assert status.error.code == 'GEMINI_NO_IMAGE'
    asyncio.run(run())


def test_daily_usage_persists_and_resets(tmp_path):
    from services.providers.gemini import DailyUsage
    day = [date(2026, 10, 5)]
    usage = DailyUsage(2, tmp_path / 'usage.json', today=lambda: day[0])
    assert usage.try_consume() and usage.try_consume() and not usage.try_consume()
    assert DailyUsage(2, tmp_path / 'usage.json', today=lambda: day[0]).remaining() == 0
    day[0] = date(2026, 10, 6)
    assert DailyUsage(2, tmp_path / 'usage.json', today=lambda: day[0]).remaining() == 2
