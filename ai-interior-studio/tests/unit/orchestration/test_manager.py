import asyncio

import pytest

from services.core.domain import (
    DomainError, JobState, Project, RenderRequest, new_job, transition,
)
from services.core.storage import ArtifactStore, DataRoot, Database, JobFiles, SNAPSHOT_NAMES
from services.core.orchestration import JobManager
from services.providers.mock import MockProvider


async def settled(manager, job_id, state):
    async with asyncio.timeout(3):
        while manager.db.jobs.get(job_id).state != state:
            await asyncio.sleep(.005)
    return manager.db.jobs.get(job_id)


def setup(tmp_path, provider, **options):
    root = DataRoot(tmp_path)
    db = Database(root.db_path)
    project = db.projects.add(Project(name='Test'))
    artifact = ArtifactStore(root).put_bytes(project.id, b'source', kind='source_scene', media_type='image/png')
    db.artifacts.add(artifact)
    request = RenderRequest(project_id=project.id, mode='sketchup_render', source={'artifact_id': artifact.id}, prompt={'raw_text': 'Interior'})
    return JobManager(db, root, [provider], poll_interval=.001, **options), request


@pytest.mark.parametrize('failure,code', [('vram', 'OUT_OF_VRAM'), ('timeout', 'JOB_TIMEOUT')])
def test_failure_retry_and_snapshots(tmp_path, failure, code):
    async def run():
        provider = MockProvider(delay=0, failure=failure)
        manager, request = setup(tmp_path, provider, timeout=.05)
        await manager.start()
        try:
            job = await manager.submit(request)
            failed = await settled(manager, job.id, JobState.FAILED)
            assert failed.error.code == code
            for name in SNAPSHOT_NAMES:
                assert manager.files.read_text(job.project_id, job.id, name)
            with pytest.raises(DomainError, match='SNAPSHOT_EXISTS'):
                manager.files.write_once(job.project_id, job.id, 'request.json', {})
            provider.failure = None
            child = await manager.retry(job.id)
            assert child.retry_of == job.id
            assert manager.db.jobs.get(job.id).state == JobState.RETRY
            await settled(manager, child.id, JobState.REVIEW)
        finally:
            await manager.stop()
            manager.db.close()
    asyncio.run(run())


def test_cancel_running_and_queued(tmp_path):
    async def run():
        manager, request = setup(tmp_path, MockProvider(delay=10))
        await manager.start()
        try:
            first = await manager.submit(request)
            await settled(manager, first.id, JobState.RUNNING)
            second = await manager.submit(request)
            assert (await manager.cancel(second.id)).state == JobState.CANCELLED
            assert (await manager.cancel(first.id)).state == JobState.CANCELLED
            await asyncio.sleep(.02)
            assert manager.db.jobs.get(first.id).state == JobState.CANCELLED
            for job in (first, second):
                for name in SNAPSHOT_NAMES:
                    assert manager.files.read_text(job.project_id, job.id, name)
        finally:
            await manager.stop()
            manager.db.close()
    asyncio.run(run())


def test_restart_reconciles_inflight(tmp_path):
    async def run():
        manager, request = setup(tmp_path, MockProvider(delay=0))
        queued = transition(new_job(request), JobState.QUEUED)
        running = transition(transition(new_job(request), JobState.QUEUED), JobState.RUNNING)
        manager.db.jobs.add(queued)
        manager.db.jobs.add(running)
        manager.db.close()
        manager = JobManager(Database(manager.root.db_path), manager.root, [MockProvider(delay=0)], poll_interval=.001)
        await manager.start()
        try:
            await settled(manager, queued.id, JobState.REVIEW)
            failed = manager.db.jobs.get(running.id)
            assert failed.state == JobState.FAILED
            assert failed.error.code == 'PROCESS_RESTARTED'
        finally:
            await manager.stop()
            manager.db.close()
    asyncio.run(run())


def test_worker_survives_provider_exception_and_shutdown(tmp_path):
    async def run():
        provider = MockProvider(delay=0)
        manager, request = setup(tmp_path, provider)
        original = provider.submit
        async def broken(_request):
            raise RuntimeError('private-token')
        provider.submit = broken
        await manager.start()
        try:
            failed = await manager.submit(request)
            job = await settled(manager, failed.id, JobState.FAILED)
            assert job.error.code == 'PROVIDER_ERROR'
            assert 'private-token' not in job.model_dump_json()
            provider.submit = original
            success = await manager.submit(request)
            await settled(manager, success.id, JobState.REVIEW)
            provider.delay = 10
            running = await manager.submit(request)
            await settled(manager, running.id, JobState.RUNNING)
            await manager.stop()
            assert manager.db.jobs.get(running.id).state == JobState.RUNNING
            await manager.start()
            assert manager.db.jobs.get(running.id).error.code == 'PROCESS_RESTARTED'
        finally:
            await manager.stop()
            manager.db.close()
    asyncio.run(run())
