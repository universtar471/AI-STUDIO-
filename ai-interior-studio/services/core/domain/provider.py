"""Provider contract (spec 4.2). Adapters live in services/providers/<name>/."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from .enums import RenderMode
from .models import JobError, Model, RenderMetrics, RenderRequest, utcnow


class ProviderCapabilities(Model):
    supported_modes: list[RenderMode]
    supports_multi_reference: bool = False
    max_reference_images: int = Field(default=0, ge=0)
    supported_ratios: list[str] = Field(default_factory=list)
    supported_sizes: list[str] = Field(default_factory=list)
    supports_seed: bool = False
    supports_negative_prompt: bool = False
    supports_local: bool = False
    has_usage_cost: bool = False  # true for paid cloud calls; drives the cost guard
    license_class: str = "unknown"


class ValidationIssue(Model):
    code: str
    message: str


class ValidationResult(Model):
    ok: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ProviderHealth(Model):
    status: HealthStatus
    detail: str | None = None
    checked_at: datetime = Field(default_factory=utcnow)


class ProviderJobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProviderJob(Model):
    provider_job_id: str
    submitted_at: datetime = Field(default_factory=utcnow)
    provider_request: dict[str, Any] = Field(default_factory=dict)  # saved as provider_request.json


class ProviderStatus(Model):
    state: ProviderJobState
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    stage: str | None = None
    message: str | None = None
    error: JobError | None = None
    metrics: RenderMetrics = Field(default_factory=RenderMetrics)


class ProviderOutput(Model):
    """Raw bytes from a provider. The orchestrator stores them; providers never write files."""

    data: bytes
    media_type: str = "image/png"
    suggested_name: str | None = None
    model: str | None = None
    seed: int | None = None


@runtime_checkable
class ImageProvider(Protocol):
    id: str
    capabilities: ProviderCapabilities

    async def health(self) -> ProviderHealth: ...
    async def validate(self, request: RenderRequest) -> ValidationResult: ...
    async def submit(self, request: RenderRequest) -> ProviderJob: ...
    async def poll(self, provider_job_id: str) -> ProviderStatus: ...
    async def cancel(self, provider_job_id: str) -> None: ...
    async def fetch_result(self, provider_job_id: str) -> list[ProviderOutput]: ...
