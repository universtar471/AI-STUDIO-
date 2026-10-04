"""Deterministic PNG provider; no network, GPU or filesystem access."""
from __future__ import annotations

import struct
import time
import zlib

from services.core.domain import (
    JobError, ProviderCapabilities, ProviderHealth, ProviderJob, ProviderOutput,
    ProviderStatus, RenderMetrics, RenderMode, RenderRequest, ValidationResult, new_id,
)

def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


PNG = (b'\x89PNG\r\n\x1a\n'
       + _chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
       + _chunk(b'IDAT', zlib.compress(b'\x00\xcc\xbb\xaa'))
       + _chunk(b'IEND', b''))


class MockProvider:
    id = 'mock'
    capabilities = ProviderCapabilities(
        supported_modes=list(RenderMode), supports_multi_reference=True,
        max_reference_images=16, supported_ratios=['16:9', '4:3', '1:1', '9:16'],
        supported_sizes=['1K', '2K', '4K'], supports_seed=True,
        supports_local=True, license_class='test-only',
    )

    def __init__(self, *, delay: float = 2.0, failure: str | None = None):
        if delay < 0 or failure not in (None, 'vram', 'timeout'):
            raise ValueError('Invalid mock delay or failure mode')
        self.delay = delay
        self.failure = failure
        self._jobs: dict[str, tuple[float, RenderRequest, str | None]] = {}
        self._cancelled: set[str] = set()

    async def health(self) -> ProviderHealth:
        return ProviderHealth(status='ok', detail='Synthetic images only')

    async def validate(self, request: RenderRequest) -> ValidationResult:
        return ValidationResult(ok=True)

    async def submit(self, request: RenderRequest) -> ProviderJob:
        identifier = new_id()
        self._jobs[identifier] = (time.monotonic(), request, self.failure)
        return ProviderJob(provider_job_id=identifier, provider_request={
            'provider': self.id, 'prompt': request.prompt.raw_text or '',
            'request': request.model_dump(mode='json'),
        })

    async def poll(self, provider_job_id: str) -> ProviderStatus:
        started, _, failure = self._jobs[provider_job_id]
        elapsed = time.monotonic() - started
        if provider_job_id in self._cancelled:
            return ProviderStatus(state='cancelled')
        if failure == 'timeout' or elapsed < self.delay:
            return ProviderStatus(state='running', progress=min(.95, elapsed / max(self.delay, .001)), stage='mock')
        if failure == 'vram':
            return ProviderStatus(state='failed', error=JobError(code='OUT_OF_VRAM', message='Mock GPU memory exhausted'))
        return ProviderStatus(state='succeeded', progress=1, metrics=RenderMetrics(duration_s=elapsed, cost_estimate=0))

    async def cancel(self, provider_job_id: str) -> None:
        self._cancelled.add(provider_job_id)

    async def fetch_result(self, provider_job_id: str) -> list[ProviderOutput]:
        if (await self.poll(provider_job_id)).state != 'succeeded':
            raise ValueError('Mock result is not ready')
        return [ProviderOutput(data=PNG, suggested_name='mock.png', model='mock', seed=self._jobs[provider_job_id][1].seed)]
