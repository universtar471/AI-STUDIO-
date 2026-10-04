"""Single-process persisted FIFO scheduler. All mutations run on its event loop."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
import time

from services.core.domain import (
    IN_FLIGHT_STATES, DomainError, ErrorCode, ImageProvider, JobError, JobProgressEvent,
    JobState, PromptSpec, ReferenceSlot, RenderJob, RenderRequest, RenderResult,
    ensure_can_finalize, new_job, retry_job, transition,
)
from services.core.prompts import build_prompt_spec, prompt_version
from services.core.storage import ArtifactStore, DataRoot, Database, JobFiles
from .selection import OrchestrationError, select_provider

log = logging.getLogger(__name__)


class JobManager:
    def __init__(self, db: Database, root: DataRoot, providers: list[ImageProvider], *, timeout: float = 120, poll_interval: float = .1):
        if timeout <= 0 or poll_interval <= 0:
            raise ValueError('Timeout and poll interval must be positive')
        self.db, self.root, self.providers = db, root, providers
        self.files, self.artifacts = JobFiles(root), ArtifactStore(root)
        self.timeout, self.poll_interval = timeout, poll_interval
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.subscribers: set[asyncio.Queue[JobProgressEvent]] = set()
        self._worker: asyncio.Task | None = None
        self._active: dict[str, asyncio.Task] = {}
        self._handles: dict[str, tuple[ImageProvider, str]] = {}

    def subscribe(self) -> asyncio.Queue[JobProgressEvent]:
        queue: asyncio.Queue[JobProgressEvent] = asyncio.Queue(maxsize=128)
        self.subscribers.add(queue)
        return queue

    def publish(self, job: RenderJob) -> None:
        event = JobProgressEvent.from_job(job, metrics=job.result.metrics.model_dump(mode='json') if job.result else {})
        for queue in self.subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    def _save(self, job: RenderJob) -> RenderJob:
        self.db.jobs.save(job)
        self.publish(job)
        return job

    def _snapshot(self, job: RenderJob, name: str, value) -> None:
        try:
            self.files.write_once(job.project_id, job.id, name, value)
        except DomainError as exc:
            if exc.code != ErrorCode.SNAPSHOT_EXISTS:
                raise

    def _inputs(self, job: RenderJob) -> None:
        self._snapshot(job, 'request.json', job.request)
        self._snapshot(job, 'refs.json', [r.model_dump(mode='json') for r in job.request.references])

    def _prompt_file(self, job: RenderJob, text: str) -> str:
        """prompt.txt holds the text the provider actually received; returns its prompt_version."""
        self._snapshot(job, 'prompt.txt', text)
        return prompt_version(job.request.prompt, text)

    def _finish_files(self, job: RenderJob, duration: float = 0, *, version: str | None = None, error_class: str | None = None) -> None:
        self._inputs(job)
        # Never submitted: fall back to the user's own text (or empty) so the snapshot set is complete.
        fallback = self._prompt_file(job, job.request.prompt.raw_text or '')
        self._snapshot(job, 'provider_request.json', {'submitted': False})
        self._snapshot(job, 'metrics.json', {
            'duration_s': duration, 'state': job.state, 'prompt_version': version or fallback,
            'error': job.error.model_dump(mode='json') if job.error else None,
            'error_class': error_class,
            'provider_metrics': job.result.metrics.model_dump(mode='json') if job.result else {},
        })

    async def start(self) -> None:
        if self._worker:
            return
        for job in self.db.jobs.list_by_state(IN_FLIGHT_STATES):
            self._inputs(job)
            if job.state == JobState.QUEUED:
                self.queue.put_nowait(job.id)
            elif job.state == JobState.RUNNING:
                failed = transition(job, JobState.FAILED, reason='Process restarted; provider execution cannot be resumed safely', error=JobError(code='PROCESS_RESTARTED', message='Process restarted during execution; retry explicitly'))
                self._finish_files(failed)
                self._save(failed)
            else:
                # Contract disallows FINALIZING -> FAILED: preserve approved preview.
                self._save(transition(job, JobState.APPROVED, reason='Process restarted during finalization; approved preview retained'))
        self._worker = asyncio.create_task(self._work())

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    def _owned(self, repo, identifier: str, project_id: str):
        obj = repo.get(identifier)
        if obj.project_id != project_id:
            raise OrchestrationError('PROJECT_MISMATCH', 'Input belongs to another project')
        return obj

    def prepare(self, request: RenderRequest) -> RenderRequest:
        self.db.projects.get(request.project_id)
        if request.source.room_id or request.mode == 'plan_concept':
            raise OrchestrationError('MODE_NOT_AVAILABLE', 'Plan and room workflows are deferred')
        if request.source.artifact_id:
            self._owned(self.db.artifacts, request.source.artifact_id, request.project_id)
        if request.source.scene_id:
            self._owned(self.db.scenes, request.source.scene_id, request.project_id)
        if request.parent_job_id:
            parent = self._owned(self.db.jobs, request.parent_job_id, request.project_id)
            if request.mode == 'upscale':
                ensure_can_finalize(parent)
            if not parent.result or not parent.result.artifact_ids:
                raise OrchestrationError('PARENT_MISSING_RESULT', 'Parent job has no image')
        elif request.mode == 'upscale':
            raise OrchestrationError('FINALIZE_REQUIRES_PARENT', 'Upscale requires an approved parent job')
        if request.style_pack_version and not request.style_pack_id:
            raise OrchestrationError('STYLE_PACK_REQUIRED', 'Version requires a Style Pack id')
        if request.style_pack_id:
            pack = self.db.style_packs.get(request.style_pack_id, request.style_pack_version)
            if pack.project_id not in (None, request.project_id):
                raise OrchestrationError('PROJECT_MISMATCH', 'Style Pack belongs to another project')
            references = request.references or [ReferenceSlot(artifact_id=r.artifact_id, role=r.role, priority=r.priority) for r in pack.references]
            request = request.model_copy(update={'style_pack_version': pack.version, 'references': references})
        for reference in request.references:
            self._owned(self.db.artifacts, reference.artifact_id, request.project_id)
        return self._with_prompt(request)

    def _with_prompt(self, request: RenderRequest) -> RenderRequest:
        """An empty prompt is built from the scene and the locked Style Pack version (A5), once, at submit.

        The built spec is stored on the job, so a retry or a restart sends the same prompt.
        """
        if request.prompt != PromptSpec() or not request.source.scene_id:
            return request
        scene = self.db.scenes.get(request.source.scene_id)
        pack = self.db.style_packs.get(request.style_pack_id, request.style_pack_version) if request.style_pack_id else None
        return request.model_copy(update={'prompt': build_prompt_spec(scene=scene, style_pack=pack)})

    def _enqueue(self, job: RenderJob) -> RenderJob:
        self.db.jobs.add(job)
        self._inputs(job)
        queued = self._save(transition(job, JobState.QUEUED))
        self.queue.put_nowait(job.id)
        return queued

    async def submit(self, request: RenderRequest) -> RenderJob:
        return self._enqueue(new_job(self.prepare(request)))

    async def retry(self, identifier: str) -> RenderJob:
        old = self.db.jobs.get(identifier)
        request = self.prepare(old.request)
        closed, child = retry_job(old, request=request)
        # Add the replacement before closing the source, so a write failure keeps it retryable.
        queued = self._enqueue(child)
        self._save(closed)
        return queued

    async def approve(self, identifier: str) -> RenderJob:
        return self._save(transition(self.db.jobs.get(identifier), JobState.APPROVED))

    async def cancel(self, identifier: str) -> RenderJob:
        job = transition(self.db.jobs.get(identifier), JobState.CANCELLED)
        self._finish_files(job)
        self._save(job)
        task = self._active.get(identifier)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        return self.db.jobs.get(identifier)

    async def _cancel_provider(self, identifier: str) -> None:
        handle = self._handles.get(identifier)
        if handle:
            with suppress(Exception):
                await asyncio.wait_for(handle[0].cancel(handle[1]), timeout=2)

    async def _work(self) -> None:
        while True:
            identifier = await self.queue.get()
            try:
                if self.db.jobs.get(identifier).state != JobState.QUEUED:
                    continue
                task = asyncio.create_task(self._execute(identifier))
                self._active[identifier] = task
                try:
                    await task
                except asyncio.CancelledError:
                    if asyncio.current_task().cancelling():
                        raise
            finally:
                self._active.pop(identifier, None)
                self._handles.pop(identifier, None)
                self.queue.task_done()

    async def _execute(self, identifier: str) -> None:
        started = time.monotonic()
        job = self._save(transition(self.db.jobs.get(identifier), JobState.RUNNING))
        version: str | None = None
        error_class: str | None = None
        provider: ImageProvider | None = None
        try:
            async with asyncio.timeout(self.timeout):
                provider = await select_provider(self.providers, job.request)
                handle = await provider.submit(job.request)
                self._handles[identifier] = (provider, handle.provider_job_id)
                self._snapshot(job, 'provider_request.json', handle.provider_request)
                sent = handle.provider_request.get('prompt')
                version = self._prompt_file(job, sent if isinstance(sent, str) else job.request.prompt.raw_text or '')
                job = self._save(job.model_copy(update={'provider_id': provider.id, 'provider_job_id': handle.provider_job_id}))
                while True:
                    status = await provider.poll(handle.provider_job_id)
                    if status.state == 'failed':
                        error = status.error or JobError(code='PROVIDER_FAILED', message='Provider failed without an error')
                        job = transition(job, JobState.FAILED, error=error)
                        break
                    if status.state == 'cancelled':
                        job = transition(job, JobState.CANCELLED, reason='Provider cancelled execution')
                        break
                    if status.state == 'succeeded':
                        outputs = await provider.fetch_result(handle.provider_job_id)
                        artifacts = []
                        for output in outputs:
                            artifact = self.artifacts.put_bytes(job.project_id, output.data, kind='final' if job.request.mode == 'upscale' else 'preview', media_type=output.media_type)
                            self.db.artifacts.add(artifact)
                            artifacts.append(artifact.id)
                        result = RenderResult(artifact_ids=artifacts, provider_id=provider.id, model=outputs[0].model if outputs else None, seed=outputs[0].seed if outputs else None, metrics=status.metrics)
                        job = transition(job, JobState.REVIEW, result=result)
                        break
                    if (status.progress, status.stage) != (job.progress, job.stage):
                        # Only real changes hit SQLite and the WebSocket; polls are frequent.
                        job = self._save(job.model_copy(update={'progress': status.progress, 'stage': status.stage}))
                    await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            await self._cancel_provider(identifier)
            # Shutdown leaves RUNNING persisted for explicit restart reconciliation.
            raise
        except TimeoutError:
            await self._cancel_provider(identifier)
            job = transition(job, JobState.FAILED, error=JobError(code='JOB_TIMEOUT', message='Job exceeded configured timeout'))
        except Exception as exc:
            await self._cancel_provider(identifier)
            code = exc.code if isinstance(exc, OrchestrationError) else 'PROVIDER_ERROR'
            # Class name only: exception messages can carry keys or request headers.
            error_class = type(exc).__name__
            log.warning('Job %s failed in provider %s: %s', identifier, provider.id if provider else '-', error_class)
            job = transition(job, JobState.FAILED, error=JobError(code=code, message='Render execution failed; inspect provider health'))
        self._finish_files(job, time.monotonic() - started, version=version, error_class=error_class)
        self._save(job)
