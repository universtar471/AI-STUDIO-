import asyncio
import json
import logging

from services.core.domain import (
    JobState, ProviderCapabilities, ProviderHealth, ProviderJob, ProviderOutput, ProviderStatus,
    Project, RenderMode, RenderRequest, Scene, StylePack, ValidationResult,
)
from services.core.orchestration import JobManager
from services.core.prompts import build_prompt_spec, prompt_version, render_flux
from services.core.storage import ArtifactStore, Database, DataRoot, SNAPSHOT_NAMES
from services.providers.mock import MockProvider

PACK_STYLE = {'style': 'Japandi', 'materials': {'floor': 'light oak'}}


class Env:
    def __init__(self, tmp_path, provider):
        self.root = DataRoot(tmp_path)
        self.db = Database(self.root.db_path)
        self.project = self.db.projects.add(Project(name='P'))
        artifact = ArtifactStore(self.root).put_bytes(self.project.id, b'scene', kind='source_scene', media_type='image/png')
        self.db.artifacts.add(artifact)
        self.scene = self.db.scenes.add(Scene(project_id=self.project.id, name='Living room', rgb_artifact_id=artifact.id))
        self.pack = self.db.style_packs.add_version(StylePack(name='Oak', project_id=self.project.id, style_prompt=PACK_STYLE))
        self.manager = JobManager(self.db, self.root, [provider], poll_interval=.001, timeout=5)

    def request(self, **kw):
        return RenderRequest(project_id=self.project.id, mode='sketchup_render', source={'scene_id': self.scene.id},
                             style_pack_id=self.pack.id, **kw)

    def read(self, job_id, name):
        return self.manager.files.read_text(self.project.id, job_id, name)

    async def settle(self, job_id, *states):
        async with asyncio.timeout(3):
            while self.db.jobs.get(job_id).state not in states:
                await asyncio.sleep(.002)
        return self.db.jobs.get(job_id)


def run(env, body):
    async def wrapper():
        await env.manager.start()
        try:
            await body()
        finally:
            await env.manager.stop()
            env.db.close()
    asyncio.run(wrapper())


def test_empty_prompt_is_built_from_scene_and_style_pack(tmp_path):
    env = Env(tmp_path, MockProvider(delay=0))

    async def body():
        job = await env.manager.submit(env.request())
        expected = build_prompt_spec(scene=env.scene, style_pack=env.pack)
        assert job.request.prompt == expected
        done = await env.settle(job.id, JobState.REVIEW)
        text = env.read(job.id, 'prompt.txt')
        assert text == render_flux(expected)
        assert 'Japandi' in text and 'light oak' in text
        metrics = json.loads(env.read(job.id, 'metrics.json'))
        assert metrics['prompt_version'] == prompt_version(expected, text)
        assert json.loads(env.read(job.id, 'provider_request.json'))['prompt'] == text
        # NÊN SỬA A2 #3: every snapshot exists for a successful job.
        for name in SNAPSHOT_NAMES:
            assert env.read(done.id, name)
    run(env, body)


def test_raw_text_is_kept_verbatim(tmp_path):
    env = Env(tmp_path, MockProvider(delay=0))

    async def body():
        job = await env.manager.submit(env.request(prompt={'raw_text': 'My exact words'}))
        assert job.request.prompt.style == ''
        await env.settle(job.id, JobState.REVIEW)
        assert env.read(job.id, 'prompt.txt') == 'My exact words'
    run(env, body)


def test_retry_reuses_the_built_prompt(tmp_path):
    env = Env(tmp_path, MockProvider(delay=0))

    async def body():
        job = await env.manager.submit(env.request())
        await env.settle(job.id, JobState.REVIEW)
        child = await env.manager.retry(job.id)
        await env.settle(child.id, JobState.REVIEW)
        assert env.read(child.id, 'prompt.txt') == env.read(job.id, 'prompt.txt')
    run(env, body)


class Broken(MockProvider):
    async def submit(self, request):
        raise KeyError('secret-token-value')


def test_provider_error_class_is_recorded_without_message(tmp_path, caplog):
    env = Env(tmp_path, Broken(delay=0))

    async def body():
        with caplog.at_level(logging.WARNING, logger='services.core.orchestration.manager'):
            job = await env.manager.submit(env.request(prompt={'raw_text': 'x'}))
            await env.settle(job.id, JobState.FAILED)
        metrics = json.loads(env.read(job.id, 'metrics.json'))
        assert metrics['error_class'] == 'KeyError'
        assert 'secret-token-value' not in json.dumps(metrics)
        assert any('KeyError' in r.getMessage() and 'mock' in r.getMessage() for r in caplog.records)
        assert all('secret-token-value' not in r.getMessage() for r in caplog.records)
        # Failed before submit: prompt.txt still exists (empty raw text fallback).
        assert env.read(job.id, 'prompt.txt') is not None
    run(env, body)


class Plateau:
    """Reports the same progress for many polls, then succeeds."""

    id = 'plateau'
    capabilities = ProviderCapabilities(supported_modes=[RenderMode.SKETCHUP_RENDER], supports_local=True,
                                        supported_ratios=['16:9'], max_reference_images=4, supports_multi_reference=True)

    def __init__(self):
        self.polls = 0

    async def health(self):
        return ProviderHealth(status='ok')

    async def validate(self, request):
        return ValidationResult(ok=True)

    async def submit(self, request):
        return ProviderJob(provider_job_id='p1', provider_request={'prompt': 'x'})

    async def poll(self, provider_job_id):
        self.polls += 1
        if self.polls >= 60:
            return ProviderStatus(state='succeeded', progress=1)
        return ProviderStatus(state='running', progress=0.5 if self.polls >= 30 else 0.2, stage='sampling')

    async def cancel(self, provider_job_id):
        pass

    async def fetch_result(self, provider_job_id):
        return [ProviderOutput(data=b'\x89PNG')]


def test_progress_saved_only_when_it_changes(tmp_path):
    provider = Plateau()
    env = Env(tmp_path, provider)
    saves = []
    original = env.db.jobs.save
    env.db.jobs.save = lambda job: (saves.append((job.state, job.progress)), original(job))[1]

    async def body():
        job = await env.manager.submit(env.request(prompt={'raw_text': 'x'}))
        await env.settle(job.id, JobState.REVIEW)
        running = [s for s in saves if s[0] == JobState.RUNNING]
        assert provider.polls == 60
        # RUNNING transition, provider id, 0.2, 0.5: four saves instead of ~60.
        assert len(running) <= 4, running
        assert [p for _, p in running][-2:] == [0.2, 0.5]
    run(env, body)
