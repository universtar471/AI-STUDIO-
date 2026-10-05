"""Google Flow provider: renders through the user's signed-in Flow web app instead of a paid API.

The browser automation is the TB Gemini Render driver shared with the SketchUp plugin (`node run.js <jobDir>`);
this provider only turns a RenderRequest into that driver's job folder and reads the result back. Flow takes the
base view plus at most one style reference (the driver's STYLE_REF slot); the prompt names them in that order
(render_gemini: Flow runs Nano Banana, the same model family). Jobs are serialised because the driver holds one
Chrome profile at a time.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Callable
import uuid

from services.core.domain import (
    HealthStatus, JobError, ProviderCapabilities, ProviderHealth, ProviderJob, ProviderJobState, ProviderOutput,
    ProviderStatus, ReferenceRole, ReferenceSlot, RenderMetrics, RenderMode, RenderRequest, ValidationIssue,
    ValidationResult, new_id,
)
from services.core.prompts import render_gemini
from services.core.prompts.builder import SCENE_PRESERVATION
from services.core.references import select_references
from services.providers.gemini import ImageSource
from .config import FlowConfig, load_config, resolve_driver
from .driver import FlowDriver, FlowError, NodeFlowDriver

_SUFFIX = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}
MAX_REFERENCES = 1  # the driver's STYLE_REF slot; LIGHT_MAP is a SketchUp-only input


class _Run:
    def __init__(self):
        self.task: asyncio.Task | None = None
        self.status = ProviderStatus(state=ProviderJobState.QUEUED)
        self.outputs: list[ProviderOutput] = []


class FlowProvider:
    id = 'flow'

    def __init__(self, images: ImageSource, *, data_root: Path, config: FlowConfig | None = None,
                 driver: FlowDriver | None = None):
        self.config = config or load_config()
        self.images = images
        self.node, self.driver_path = resolve_driver(self.config)
        data_root = Path(data_root)
        self._driver = driver or (NodeFlowDriver(
            node=self.node, driver=self.driver_path, jobs_dir=data_root / 'flow-jobs', project_url=self.config.project_url,
            project_id=str(uuid.uuid5(uuid.NAMESPACE_URL, 'ai-interior-studio/flow')),
            project_name=self.config.project_name, ratios=self.config.supported_ratios,
            download_resolution=self.config.download_resolution, timeout_s=self.config.timeout_s)
            if self.driver_path else None)
        self.capabilities = ProviderCapabilities(
            supported_modes=[RenderMode.SKETCHUP_RENDER, RenderMode.IMAGE_EDIT],
            supports_multi_reference=False, max_reference_images=MAX_REFERENCES,
            supported_ratios=list(self.config.supported_ratios), supported_sizes=[],
            supports_seed=False, supports_local=False, has_usage_cost=False, license_class='cloud-web',
        )
        self._queue = asyncio.Lock()
        self._runs: dict[str, _Run] = {}

    # --- contract ------------------------------------------------------------------

    async def health(self) -> ProviderHealth:
        # No browser launch here: health is polled often. Sign-in problems surface on the first job.
        if self._driver is None:
            return ProviderHealth(status=HealthStatus.UNAVAILABLE,
                                  detail='TB Gemini Render driver not found (install the SketchUp plugin or set driver_path)')
        if isinstance(self._driver, NodeFlowDriver) and not self._driver.driver.is_file():
            return ProviderHealth(status=HealthStatus.UNAVAILABLE, detail=f'Flow driver missing: {self._driver.driver}')
        return ProviderHealth(status=HealthStatus.OK, detail='Google Flow via the TB Gemini Render driver')

    async def validate(self, request: RenderRequest) -> ValidationResult:
        errors = []
        if request.mode not in self.capabilities.supported_modes:
            errors.append(ValidationIssue(code='FLOW_MODE_UNSUPPORTED', message=f'Mode {request.mode} is not supported'))
        if request.ratio not in self.config.supported_ratios:
            errors.append(ValidationIssue(code='FLOW_RATIO_UNSUPPORTED', message=f'Ratio {request.ratio} is not offered by Flow'))
        if request.image_size:
            errors.append(ValidationIssue(code='FLOW_SIZE_UNSUPPORTED', message='Flow has no output size setting'))
        return ValidationResult(ok=not errors, errors=errors)

    async def submit(self, request: RenderRequest) -> ProviderJob:
        validation = await self.validate(request)
        if not validation.ok:
            raise ValueError(validation.errors[0].code)
        identifier = new_id()
        job, record = self._build(request, identifier)
        run = _Run()
        self._runs[identifier] = run
        run.task = asyncio.create_task(self._execute(run, job))
        return ProviderJob(provider_job_id=identifier, provider_request=record)

    async def poll(self, provider_job_id: str) -> ProviderStatus:
        return self._runs[provider_job_id].status

    async def cancel(self, provider_job_id: str) -> None:
        # A generation already sent to Flow cannot be recalled; the result is simply dropped.
        run = self._runs.get(provider_job_id)
        if run and run.task and not run.task.done():
            run.task.cancel()
        if run and run.status.state in (ProviderJobState.QUEUED, ProviderJobState.RUNNING):
            run.status = ProviderStatus(state=ProviderJobState.CANCELLED)

    async def fetch_result(self, provider_job_id: str) -> list[ProviderOutput]:
        run = self._runs[provider_job_id]
        if run.status.state != ProviderJobState.SUCCEEDED:
            raise ValueError('Flow result is not ready')
        return list(run.outputs)

    # --- internals -----------------------------------------------------------------

    def _build(self, request: RenderRequest, identifier: str):
        base_id, base_data, base_mime = self.images.base_image(request)
        selection = select_references([r for r in request.references if r.role != ReferenceRole.BASE_PLAN], MAX_REFERENCES)
        slots = [ReferenceSlot(artifact_id=base_id, role=ReferenceRole.BASE_PLAN), *selection.selected]
        style = None
        if selection.selected:
            data, mime = self.images.image(selection.selected[0].artifact_id)
            style = (data, mime)
        spec = request.prompt
        if not spec.raw_text and not spec.preservation:
            spec = spec.model_copy(update={'preservation': list(SCENE_PRESERVATION)})
        prompt = render_gemini(spec, slots, extra=selection.summary)
        job = {'id': identifier, 'base': (base_data, base_mime), 'style': style, 'prompt': prompt,
               'scene_name': f'ais-{identifier[:8]}'}
        sources = [(base_id, base_data)] + ([(selection.selected[0].artifact_id, style[0])] if style else [])
        record = {'provider': self.id, 'driver': 'tb-gemini-render', 'prompt': prompt, 'ratio': request.ratio,
                  'images': [{'index': i + 1, 'role': slot.role.value, 'artifact_id': aid,
                              'sha256': hashlib.sha256(data).hexdigest()}
                             for i, (slot, (aid, data)) in enumerate(zip(slots, sources))],
                  'dropped_references': [s.artifact_id for s in selection.dropped]}
        return job, record

    async def _execute(self, run: _Run, job: dict):
        loop = asyncio.get_running_loop()
        started = loop.time()

        def progress(stage: str, value: float):
            loop.call_soon_threadsafe(setattr, run, 'status', ProviderStatus(state=ProviderJobState.RUNNING, stage=f'flow:{stage}', progress=value))

        async with self._queue:
            run.status = ProviderStatus(state=ProviderJobState.RUNNING, stage='flow:queued', progress=0.01)
            if self._driver is None:
                run.status = _failed('FLOW_DRIVER_MISSING', 'TB Gemini Render driver not found', retryable=False)
                return
            try:
                data, media, info = await asyncio.to_thread(self._driver.render, job, progress)
            except FlowError as exc:
                run.status = _failed(exc.code, exc.message, exc.retryable)
                return
            except Exception as exc:  # only the class name: driver output may carry account details
                run.status = _failed('FLOW_ERROR', f'Flow automation failed ({type(exc).__name__})')
                return
        duration = loop.time() - started
        run.outputs = [ProviderOutput(data=data, media_type=media, suggested_name=f'flow-{job["id"][:12]}{_SUFFIX.get(media, ".png")}',
                                      model='flow')]
        run.status = ProviderStatus(state=ProviderJobState.SUCCEEDED, progress=1, metrics=RenderMetrics(
            duration_s=duration, extra={'driver': 'tb-gemini-render', 'duration_s': duration, **info}))


def _failed(code: str, message: str, retryable: bool = True) -> ProviderStatus:
    return ProviderStatus(state=ProviderJobState.FAILED, error=JobError(code=code, message=message, retryable=retryable))
