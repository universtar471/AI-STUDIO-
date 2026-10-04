"""Gemini image provider (google-genai SDK): optional cloud path with a hard cost cap.

Images go out in a fixed order (base view first, then references as packed by A5) and the prompt
names each image's role in that same order. The provider never writes images or URLs; it returns bytes.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Callable, Protocol

from services.core.domain import (
    HealthStatus, JobError, ProviderCapabilities, ProviderHealth, ProviderJob, ProviderJobState,
    ProviderOutput, ProviderStatus, ReferenceRole, ReferenceSlot, RenderMetrics, RenderMode,
    RenderRequest, ValidationIssue, ValidationResult, new_id,
)
from services.core.prompts import render_gemini
from services.core.prompts.builder import SCENE_PRESERVATION
from services.core.references import select_references
from services.core.secrets import get_secret, redact
from .config import GeminiConfig, load_config
from .usage import DailyUsage


class ImageSource(Protocol):
    """Gives the provider the bytes it must upload. The orchestrator side owns storage."""

    def base_image(self, request: RenderRequest) -> tuple[str, bytes, str]: ...  # (artifact_id, data, mime)
    def image(self, artifact_id: str) -> tuple[bytes, str]: ...  # (data, mime)


def _default_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


class _Run:
    def __init__(self, fingerprint: str):
        self.fingerprint = fingerprint
        self.task: asyncio.Task | None = None
        self.status = ProviderStatus(state=ProviderJobState.QUEUED)
        self.outputs: list[ProviderOutput] = []


class GeminiImageProvider:
    id = 'gemini'

    def __init__(
        self,
        images: ImageSource,
        *,
        config: GeminiConfig | None = None,
        usage_path=None,
        api_key: Callable[[], str | None] = lambda: get_secret('gemini'),
        client_factory: Callable[[str], Any] = _default_client,
        today=None,
    ):
        self.config = config or load_config()
        self.images, self._api_key, self._client_factory = images, api_key, client_factory
        self.usage = DailyUsage(self.config.daily_call_limit, usage_path, **({'today': today} if today else {}))
        self.capabilities = ProviderCapabilities(
            supported_modes=[RenderMode.SKETCHUP_RENDER, RenderMode.IMAGE_EDIT, RenderMode.PLAN_CONCEPT],
            supports_multi_reference=True,
            max_reference_images=self.config.max_reference_images - 1,  # one slot is the base image
            supported_ratios=list(self.config.supported_ratios),
            supported_sizes=list(self.config.supported_sizes),
            supports_seed=True, supports_local=False, has_usage_cost=True, license_class='cloud-api',
        )
        self._runs: dict[str, _Run] = {}
        self._by_fingerprint: dict[str, str] = {}

    # --- contract ------------------------------------------------------------------

    async def health(self) -> ProviderHealth:
        if not self._api_key():
            return ProviderHealth(status=HealthStatus.UNAVAILABLE, detail='No Gemini API key: set GEMINI_API_KEY or store it in the keyring')
        # No network call here: health is polled often and must not spend quota.
        return ProviderHealth(status=HealthStatus.OK, detail=f'{self.usage.remaining()} of {self.config.daily_call_limit} calls left today')

    async def validate(self, request: RenderRequest) -> ValidationResult:
        errors = []
        size = self._size(request)
        if size not in self.config.supported_sizes:
            errors.append(ValidationIssue(code='GEMINI_SIZE_UNSUPPORTED', message=f'Size {size} is not enabled'))
        if size in self.config.high_cost_sizes and not request.confirm_high_cost:
            errors.append(ValidationIssue(code='HIGH_COST_NOT_CONFIRMED', message=f'{size} output needs confirm_high_cost = true'))
        if request.ratio not in self.config.supported_ratios:
            errors.append(ValidationIssue(code='GEMINI_RATIO_UNSUPPORTED', message=f'Ratio {request.ratio} is not supported'))
        return ValidationResult(ok=not errors, errors=errors)

    async def submit(self, request: RenderRequest) -> ProviderJob:
        validation = await self.validate(request)
        if not validation.ok:
            raise ValueError(validation.errors[0].code)
        payload, contents, record = self._build(request)
        fingerprint = record['fingerprint']
        existing = self._by_fingerprint.get(fingerprint)
        if existing and self._runs[existing].status.state not in (ProviderJobState.FAILED, ProviderJobState.CANCELLED):
            # Same request again (e.g. resubmitted after a timeout upstream): reuse, do not pay twice.
            return ProviderJob(provider_job_id=existing, provider_request={**record, 'reused_run': True})
        identifier = new_id()
        run = _Run(fingerprint)
        self._runs[identifier] = run
        self._by_fingerprint[fingerprint] = identifier
        run.task = asyncio.create_task(self._execute(run, payload, contents, record))
        return ProviderJob(provider_job_id=identifier, provider_request=record)

    async def poll(self, provider_job_id: str) -> ProviderStatus:
        return self._runs[provider_job_id].status

    async def cancel(self, provider_job_id: str) -> None:
        run = self._runs.get(provider_job_id)
        if run and run.task and not run.task.done():
            run.task.cancel()
        if run and run.status.state in (ProviderJobState.QUEUED, ProviderJobState.RUNNING):
            run.status = ProviderStatus(state=ProviderJobState.CANCELLED)

    async def fetch_result(self, provider_job_id: str) -> list[ProviderOutput]:
        run = self._runs[provider_job_id]
        if run.status.state != ProviderJobState.SUCCEEDED:
            raise ValueError('Gemini result is not ready')
        return list(run.outputs)

    # --- internals -----------------------------------------------------------------

    def _size(self, request: RenderRequest) -> str:
        return request.image_size or self.config.default_size

    def _build(self, request: RenderRequest):
        """Return (call kwargs, ordered image parts, provider_request record). Bytes never enter the record."""
        base_id, base_data, base_mime = self.images.base_image(request)
        selection = select_references(
            [r for r in request.references if r.role != ReferenceRole.BASE_PLAN],
            self.capabilities.max_reference_images,
        )
        slots = [ReferenceSlot(artifact_id=base_id, role=ReferenceRole.BASE_PLAN), *selection.selected]
        images = [(base_id, base_data, base_mime)] + [(s.artifact_id, *self.images.image(s.artifact_id)) for s in selection.selected]
        spec = request.prompt
        if not spec.raw_text and not spec.preservation:
            # An empty spec still has to tell Gemini to keep the base view's geometry.
            spec = spec.model_copy(update={'preservation': list(SCENE_PRESERVATION)})
        text = render_gemini(spec, slots, extra=selection.summary)
        size = self._size(request)
        image_records = [
            {'index': i + 1, 'role': slot.role.value, 'artifact_id': artifact_id,
             'sha256': hashlib.sha256(data).hexdigest(), 'media_type': mime}
            for i, (slot, (artifact_id, data, mime)) in enumerate(zip(slots, images))
        ]
        config = {'response_modalities': ['IMAGE'], 'image_config': {'image_size': size, 'aspect_ratio': request.ratio}}
        if request.seed is not None:
            config['seed'] = request.seed
        fingerprint = hashlib.sha256(json.dumps(
            {'model': self.config.model, 'config': config, 'prompt': text, 'images': [r['sha256'] for r in image_records]},
            sort_keys=True).encode()).hexdigest()
        record = {'provider': self.id, 'model': self.config.model, 'config': config, 'prompt': text,
                  'images': image_records, 'dropped_references': [s.artifact_id for s in selection.dropped],
                  'fingerprint': fingerprint, 'estimated_cost_usd': self.config.cost_per_image_usd.get(size)}
        payload = {'model': self.config.model, 'config': config, 'text': text}
        return payload, [(data, mime) for _, data, mime in images], record

    async def _execute(self, run: _Run, payload: dict, images: list[tuple[bytes, str]], record: dict) -> None:
        key = self._api_key()
        if not key:
            run.status = _failed('GEMINI_NO_API_KEY', 'No Gemini API key configured', retryable=False)
            return
        from google.genai import types
        contents = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in images]
        contents.append(payload['text'])
        cfg = payload['config']
        config = types.GenerateContentConfig(
            response_modalities=cfg['response_modalities'],
            image_config=types.ImageConfig(**cfg['image_config']),
            **({'seed': cfg['seed']} if 'seed' in cfg else {}),
        )
        client = self._client_factory(key)
        attempts = 0
        run.status = ProviderStatus(state=ProviderJobState.RUNNING, stage='gemini', progress=0.1)
        while True:
            if not self.usage.try_consume():
                run.status = _failed('GEMINI_DAILY_LIMIT', f'Daily Gemini call limit ({self.config.daily_call_limit}) reached', retryable=False)
                return
            attempts += 1
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(model=payload['model'], contents=contents, config=config),
                    timeout=self.config.timeout_s)
                break
            except asyncio.TimeoutError:
                if attempts >= self.config.max_attempts:
                    run.status = _failed('GEMINI_TIMEOUT', f'No answer after {attempts} attempt(s)')
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Only the class name survives: SDK errors can echo request headers.
                run.status = _failed('GEMINI_API_ERROR', redact(f'Gemini call failed ({type(exc).__name__})', [key]))
                return
        outputs = _images_from(response)
        if not outputs:
            run.status = _failed('GEMINI_NO_IMAGE', 'Gemini returned no image (possibly blocked by safety filters)')
            return
        size = cfg['image_config']['image_size']
        run.outputs = [o.model_copy(update={'model': payload['model'], 'seed': cfg.get('seed')}) for o in outputs]
        run.status = ProviderStatus(state=ProviderJobState.SUCCEEDED, progress=1, metrics=RenderMetrics(
            cost_estimate=round(self.config.cost_per_image_usd.get(size, 0) * len(outputs), 4),
            extra={'model': payload['model'], 'image_size': size, 'attempts': attempts,
                   'fingerprint': record['fingerprint'], 'usage': _usage(response)},
        ))


def _failed(code: str, message: str, retryable: bool = True) -> ProviderStatus:
    return ProviderStatus(state=ProviderJobState.FAILED, error=JobError(code=code, message=message, retryable=retryable))


def _images_from(response) -> list[ProviderOutput]:
    outputs = []
    for candidate in getattr(response, 'candidates', None) or []:
        content = getattr(candidate, 'content', None)
        for part in getattr(content, 'parts', None) or []:
            inline = getattr(part, 'inline_data', None)
            if inline is not None and getattr(inline, 'data', None):
                outputs.append(ProviderOutput(data=inline.data, media_type=inline.mime_type or 'image/png',
                                              suggested_name=f'gemini-{len(outputs) + 1}.png'))
    return outputs


def _usage(response) -> dict[str, Any]:
    meta = getattr(response, 'usage_metadata', None)
    if meta is None:
        return {}
    fields = ('prompt_token_count', 'candidates_token_count', 'total_token_count')
    return {f: getattr(meta, f) for f in fields if getattr(meta, f, None) is not None}
