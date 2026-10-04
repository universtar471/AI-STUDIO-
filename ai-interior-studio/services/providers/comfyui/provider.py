"""Async ComfyUI jobs with per-job sockets and immutable submission snapshots."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from typing import Protocol
from urllib.parse import quote

import httpx
from websockets.asyncio.client import connect

from services.core.domain import (
    HealthStatus, JobError, ProviderCapabilities, ProviderHealth, ProviderJob, ProviderJobState,
    ProviderOutput, ProviderStatus, Quality, ReferenceRole, RenderMetrics, RenderMode,
    RenderRequest, ValidationIssue, ValidationResult, new_id,
)
from services.core.prompts import render_flux
from services.core.references import select_references
from .config import ComfyUIConfig, load_config
from .manifest import contained_path, inject, load_workflow


class ImageSource(Protocol):
    def base_image(self, request: RenderRequest) -> tuple[str, bytes, str]: ...
    def image(self, artifact_id: str) -> tuple[bytes, str]: ...


class ExecutionError(Exception):
    def __init__(self, data):
        text = str(data.get('exception_type', '')) + ' ' + str(data.get('exception_message', ''))
        self.oom = 'outofmemory' in text.lower() or 'cuda out of memory' in text.lower()
        super().__init__('ComfyUI ran out of memory' if self.oom else 'ComfyUI execution failed')


class _Run:
    def __init__(self):
        self.task = None
        self.status = ProviderStatus(state=ProviderJobState.QUEUED)
        self.outputs = []


class ComfyUIProvider:
    id = 'comfyui'

    def __init__(self, images: ImageSource, *, config: ComfyUIConfig | None = None,
                 transport=None, ws_connect=connect):
        self.images = images
        self.config = config or load_config()
        self._transport, self._ws_connect = transport, ws_connect
        self._runs: dict[str, _Run] = {}
        self._queue = asyncio.Lock()
        self.capabilities = ProviderCapabilities(
            supported_modes=[RenderMode.SKETCHUP_RENDER, RenderMode.IMAGE_EDIT],
            supports_multi_reference=True, supports_seed=True, supports_local=True,
            supported_sizes=['1024', '1536'], license_class='workflow-defined',
        )
        try:
            manifest, _, _ = load_workflow(self.config)
            self.capabilities = self.capabilities.model_copy(update={'max_reference_images': manifest.max_reference_images})
        except (OSError, ValueError):
            pass  # An unconfigured provider remains constructible and reports unavailable.

    def _client(self):
        return httpx.AsyncClient(base_url=self.config.url + '/', transport=self._transport,
                                 timeout=self.config.timeout_s, trust_env=False)

    async def health(self) -> ProviderHealth:
        try:
            manifest, template, _ = load_workflow(self.config)
            async with self._client() as client:
                response = await client.get('object_info')
                response.raise_for_status()
                info = response.json()
            missing = []
            for name in sorted({n['class_type'] for n in template.values()} | {n.class_type for n in manifest.custom_nodes}):
                if name not in info:
                    missing.append(f'Missing node: {name}')
            for model in manifest.models:
                if self.config.models_dir is not None:
                    path = contained_path(self.config.models_dir, model.path)
                    if not path.is_file():
                        missing.append(f'Missing model: {model.path}')
                    elif model.sha256:
                        with path.open('rb') as stream:
                            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
                        if checksum != model.sha256.lower():
                            missing.append(f'Model checksum mismatch: {model.path}')
                else:
                    lookup = model.object_info
                    found = False
                    if lookup:
                        inputs = info.get(lookup.class_type, {}).get('input', {})
                        entry = {**inputs.get('required', {}), **inputs.get('optional', {})}.get(lookup.input, [])
                        choices = entry[0] if entry and isinstance(entry[0], list) else []
                        # ComfyUI loader combos are relative to their model category.
                        name = model.path.split('/', 1)[-1]
                        found = name in [str(v).replace('\\', '/') for v in choices]
                    if not found:
                        missing.append(f'Missing model (object_info): {model.path}')
            return ProviderHealth(status=HealthStatus.UNAVAILABLE if missing else HealthStatus.OK,
                                  detail='; '.join(missing) if missing else 'ComfyUI workflow ready')
        except (OSError, ValueError) as exc:
            return ProviderHealth(status=HealthStatus.UNAVAILABLE, detail=str(exc))
        except httpx.HTTPError:
            return ProviderHealth(status=HealthStatus.UNAVAILABLE, detail='ComfyUI offline or HTTP endpoint unavailable')
        except (KeyError, TypeError):
            return ProviderHealth(status=HealthStatus.UNAVAILABLE, detail='Invalid ComfyUI object_info or template')

    def _preset(self, request):
        if request.image_size:
            return {'1024': 'PREVIEW_FAST', '1536': 'PREVIEW_QUALITY'}[request.image_size]
        return 'PREVIEW_FAST' if request.quality == Quality.DRAFT else 'PREVIEW_QUALITY'

    async def validate(self, request):
        errors = []
        if request.mode not in self.capabilities.supported_modes or request.quality == Quality.FINAL:
            errors.append(ValidationIssue(code='COMFYUI_MODE_UNSUPPORTED', message='Only image preview and editing are supported'))
        if request.image_size not in (None, '1024', '1536'):
            errors.append(ValidationIssue(code='COMFYUI_SIZE_UNSUPPORTED', message='Expected 1024 or 1536'))
        try:
            load_workflow(self.config)
        except (OSError, ValueError) as exc:
            errors.append(ValidationIssue(code='COMFYUI_WORKFLOW_UNAVAILABLE', message=str(exc)))
        return ValidationResult(ok=not errors, errors=errors)

    async def submit(self, request):
        validation = await self.validate(request)
        if not validation.ok:
            raise ValueError(validation.errors[0].message)
        manifest, template, checksum = load_workflow(self.config)
        selection = select_references([r for r in request.references if r.role != ReferenceRole.BASE_PLAN], manifest.max_reference_images)
        base_id, data, mime = self.images.base_image(request)
        images = [(base_id, data, mime), *[(r.artifact_id, *self.images.image(r.artifact_id)) for r in selection.selected]]
        roles = [ReferenceRole.BASE_PLAN, *[r.role for r in selection.selected]]
        identifier = new_id()
        seed = request.seed if request.seed is not None else secrets.randbits(63)
        preset = self._preset(request)
        record = {'provider': self.id, 'workflow': manifest.name, 'preset': preset, 'seed': seed,
                  'prompt': render_flux(request.prompt, extra=selection.summary), 'template_sha256': checksum,
                  'filename_prefix': f'studio-{identifier}',
                  'images': [{'role': role.value, 'artifact_id': aid, 'sha256': hashlib.sha256(data).hexdigest()}
                             for role, (aid, data, _) in zip(roles, images)],
                  'dropped_references': [r.artifact_id for r in selection.dropped]}
        run = _Run()
        self._runs[identifier] = run
        run.task = asyncio.create_task(self._execute(run, manifest, template, images, record))
        return ProviderJob(provider_job_id=identifier, provider_request=record)

    async def poll(self, provider_job_id):
        return self._runs[provider_job_id].status

    async def cancel(self, provider_job_id):
        run = self._runs.get(provider_job_id)
        if run and run.status.state in (ProviderJobState.QUEUED, ProviderJobState.RUNNING):
            run.task.cancel()
            run.status = ProviderStatus(state=ProviderJobState.CANCELLED)
            try:
                await run.task
            except asyncio.CancelledError:
                pass

    async def fetch_result(self, provider_job_id):
        run = self._runs[provider_job_id]
        if run.status.state != ProviderJobState.SUCCEEDED:
            raise ValueError('ComfyUI result is not ready')
        return list(run.outputs)

    async def _execute(self, run, manifest, template, images, record):
        started = time.monotonic()
        extra = {'template_sha256': record['template_sha256'],
                 'checkpoint_sha256': {m.path: m.sha256 for m in manifest.models if m.sha256},
                 'custom_nodes': {n.class_type: n.version for n in manifest.custom_nodes},
                 'preset': record['preset'], 'vram_fallback': False, 'attempts': 0}
        def metrics():
            duration = time.monotonic() - started
            return RenderMetrics(duration_s=duration, extra={**extra, 'duration_s': duration})
        try:
            async with self._queue:
                run.status = ProviderStatus(state=ProviderJobState.RUNNING, stage='upload')
                async with asyncio.timeout(self.config.timeout_s), self._client() as client:
                    uploaded = []
                    for index, (_, data, mime) in enumerate(images):
                        suffix = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}.get(mime)
                        if suffix is None:
                            raise ValueError('Unsupported source image media type')
                        response = await client.post('upload/image', files={'image': (f'{record["filename_prefix"]}-{index}{suffix}', data, mime)}, data={'type': 'input', 'overwrite': 'false'})
                        response.raise_for_status()
                        upload = response.json()
                        uploaded.append('/'.join(filter(None, [upload.get('subfolder', ''), upload['name']])))
                    while True:
                        extra['attempts'] += 1
                        graph = inject(template, manifest, source_image=uploaded[0], reference_image=uploaded[1:],
                                       prompt=record['prompt'], seed=record['seed'], filename_prefix=record['filename_prefix'], preset=extra['preset'])
                        try:
                            run.outputs = await self._attempt(client, run, graph, record)
                            break
                        except ExecutionError as exc:
                            if not exc.oom or extra['preset'] != 'PREVIEW_QUALITY':
                                raise
                            extra.update(preset='PREVIEW_FAST', vram_fallback=True)
            run.status = ProviderStatus(state=ProviderJobState.SUCCEEDED, progress=1, metrics=metrics())
        except asyncio.CancelledError:
            run.status = ProviderStatus(state=ProviderJobState.CANCELLED, metrics=metrics())
            raise
        except Exception as exc:
            code = 'COMFYUI_ERROR'
            if isinstance(exc, ExecutionError):
                code = 'COMFYUI_OUT_OF_MEMORY' if exc.oom else 'COMFYUI_EXECUTION_ERROR'
            elif isinstance(exc, (TimeoutError, httpx.TimeoutException)):
                code = 'COMFYUI_TIMEOUT'
            run.status = ProviderStatus(state=ProviderJobState.FAILED, metrics=metrics(),
                                        error=JobError(code=code, message=f'ComfyUI job failed ({type(exc).__name__})'))

    async def _attempt(self, client, run, graph, record):
        client_id = new_id()
        ws_url = self.config.url.replace('http:', 'ws:', 1).replace('https:', 'wss:', 1) + '/ws?clientId=' + client_id
        async with self._ws_connect(ws_url, open_timeout=self.config.timeout_s) as ws:
            response = await client.post('prompt', json={'prompt': graph, 'client_id': client_id})
            response.raise_for_status()
            prompt_id = response.json()['prompt_id']
            while True:
                raw = await ws.recv()
                if isinstance(raw, bytes):
                    continue
                event = json.loads(raw)
                data = event.get('data', {})
                if data.get('prompt_id') != prompt_id:
                    continue
                if event['type'] == 'execution_error':
                    raise ExecutionError(data)
                if event['type'] == 'progress':
                    progress = min(.99, max(0., data['value'] / max(1, data['max'])))
                    run.status = ProviderStatus(state=ProviderJobState.RUNNING, progress=progress, stage='comfyui')
                elif event['type'] == 'executing':
                    if data.get('node') is None:
                        break
                    run.status = run.status.model_copy(update={'stage': f'node:{data["node"]}'})
        response = await client.get('history/' + quote(prompt_id, safe=''))
        response.raise_for_status()
        history = response.json()[prompt_id]
        for kind, data in history.get('status', {}).get('messages', []):
            if kind == 'execution_error':
                raise ExecutionError(data)
        outputs = []
        for node in history.get('outputs', {}).values():
            for image in node.get('images', []):
                if image.get('type') != 'output':
                    continue
                response = await client.get('view', params={key: image[key] for key in ('filename', 'subfolder', 'type')})
                response.raise_for_status()
                outputs.append(ProviderOutput(data=response.content, media_type=response.headers.get('content-type', 'image/png').split(';')[0],
                                              suggested_name=image['filename'], seed=record['seed']))
        if not outputs:
            raise ValueError('ComfyUI returned no output images')
        return outputs
