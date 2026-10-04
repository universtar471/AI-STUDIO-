"""WebSocket events (spec section 8)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .enums import JobState
from .models import Model, RenderJob


class JobProgressEvent(Model):
    type: Literal["job.progress"] = "job.progress"
    job_id: str
    state: JobState
    progress: float = Field(ge=0.0, le=1.0)
    stage: str | None = None
    message: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_job(cls, job: RenderJob, *, message: str | None = None, metrics: dict[str, Any] | None = None) -> "JobProgressEvent":
        return cls(job_id=job.id, state=job.state, progress=job.progress, stage=job.stage, message=message, metrics=metrics or {})
