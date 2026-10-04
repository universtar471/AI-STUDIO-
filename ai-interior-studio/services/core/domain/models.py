"""Domain models. All are frozen: change them with model_copy(update=...)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import (
    ROLE_DEFAULT_PRIORITY,
    ArtifactKind,
    JobState,
    ProjectType,
    ProviderPolicy,
    Quality,
    ReferenceRole,
    RenderMode,
)


def new_id() -> str:
    return uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Project -----------------------------------------------------------------

class Project(Model):
    id: str = Field(default_factory=new_id)
    name: str = Field(min_length=1)
    type: ProjectType = ProjectType.APARTMENT
    location_note: str | None = None
    archived: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# --- Artifact ----------------------------------------------------------------

class Artifact(Model):
    """A record pointing at an immutable blob. Records are insert-only."""

    id: str = Field(default_factory=new_id)
    project_id: str
    sha256: str = Field(min_length=64, max_length=64)
    ext: str = ""
    kind: ArtifactKind
    media_type: str
    size_bytes: int = Field(ge=0)
    original_name: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


# --- References and Style Pack -------------------------------------------------

class ReferenceSlot(Model):
    """A reference as it travels inside a RenderRequest."""

    artifact_id: str
    role: ReferenceRole
    priority: int = Field(ge=0, le=100)

    @model_validator(mode="before")
    @classmethod
    def _default_priority(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("priority") is None and "role" in data:
            data = {**data, "priority": ROLE_DEFAULT_PRIORITY[ReferenceRole(data["role"])]}
        return data


class Reference(ReferenceSlot):
    """A reference as stored in a Style Pack or attached to a room."""

    id: str = Field(default_factory=new_id)
    room_id: str | None = None  # None = project-wide
    tags: list[str] = Field(default_factory=list)
    source_note: str | None = None
    usage_rights_note: str | None = None
    quality_warnings: list[str] = Field(default_factory=list)


class StylePack(Model):
    """Versioned. A change creates a new version; old versions are never edited."""

    id: str = Field(default_factory=new_id)
    version: int = Field(default=1, ge=1)
    project_id: str | None = None
    name: str = Field(min_length=1)
    references: list[Reference] = Field(default_factory=list)
    palette: list[str] = Field(default_factory=list)
    style_prompt: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)

    def next_version(self, **changes: Any) -> "StylePack":
        return self.model_copy(update={**changes, "version": self.version + 1, "created_at": utcnow()})


# --- Scene (Mode A) and Room (Mode B) ------------------------------------------

Vec3 = tuple[float, float, float]


class CameraMeta(Model):
    eye: Vec3
    target: Vec3
    up: Vec3 = (0.0, 0.0, 1.0)
    fov_deg: float | None = Field(default=None, gt=0, lt=180)
    focal_length_mm: float | None = Field(default=None, gt=0)
    aspect_ratio: str
    viewport_width: int = Field(gt=0)
    viewport_height: int = Field(gt=0)


class Scene(Model):
    id: str = Field(default_factory=new_id)
    project_id: str
    name: str
    rgb_artifact_id: str
    camera: CameraMeta | None = None
    model_checksum: str | None = None
    # V2 passes, keyed by "depth" | "edge" | "material_id" | "object_id".
    pass_artifact_ids: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class Opening(Model):
    kind: str  # "door" | "window"
    x_mm: float
    y_mm: float
    width_mm: float = Field(gt=0)
    height_mm: float | None = Field(default=None, gt=0)


class CameraHint(Model):
    x: float
    y: float
    dir_x: float
    dir_y: float
    lens: str | None = None
    note: str | None = None


class Room(Model):
    id: str = Field(default_factory=new_id)
    project_id: str
    name: str
    room_type: str
    crop_artifact_id: str
    width_mm: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)
    ceiling_height_mm: float | None = Field(default=None, gt=0)
    openings: list[Opening] = Field(default_factory=list)
    camera_hint: CameraHint | None = None
    daylight_hint: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


# --- Render request ------------------------------------------------------------

class SourceRef(Model):
    artifact_id: str | None = None
    scene_id: str | None = None
    room_id: str | None = None


class CameraIntent(Model):
    preset: str | None = None
    height_mm: int | None = Field(default=None, gt=0)


class PromptSpec(Model):
    """Structured prompt, spec section 1.2. Each provider renders it its own way."""

    scene_facts: dict[str, Any] = Field(default_factory=dict)
    preservation: list[str] = Field(default_factory=list)
    style: str = ""
    materials: dict[str, Any] = Field(default_factory=dict)
    lighting: dict[str, Any] = Field(default_factory=dict)
    camera: dict[str, Any] = Field(default_factory=dict)
    quality: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    raw_text: str | None = None  # user's final edit from the Advanced panel


class RenderRequest(Model):
    project_id: str
    mode: RenderMode
    source: SourceRef = Field(default_factory=SourceRef)
    camera: CameraIntent | None = None
    references: list[ReferenceSlot] = Field(default_factory=list)
    prompt: PromptSpec = Field(default_factory=PromptSpec)
    quality: Quality = Quality.PREVIEW
    ratio: str = "16:9"
    image_size: str | None = None  # "1K" | "2K" | "4K" where the provider uses it
    provider_policy: ProviderPolicy = ProviderPolicy.AUTO
    provider_id: str | None = None  # explicit choice from the Advanced panel
    seed: int | None = None
    style_pack_id: str | None = None
    style_pack_version: int | None = None
    confirm_high_cost: bool = False  # must be true for paid 4K calls
    parent_job_id: str | None = None  # the job whose output this job edits or upscales

    @model_validator(mode="after")
    def _check_inputs(self) -> "RenderRequest":
        if self.mode in (RenderMode.UPSCALE, RenderMode.IMAGE_EDIT):
            if not (self.parent_job_id or self.source.artifact_id):
                raise ValueError(f"mode {self.mode} needs parent_job_id or source.artifact_id")
        elif not (self.source.artifact_id or self.source.scene_id or self.source.room_id):
            raise ValueError(f"mode {self.mode} needs a source artifact, scene or room")
        return self


# --- Render job ----------------------------------------------------------------

class RenderMetrics(Model):
    duration_s: float | None = None
    vram_mb: int | None = None
    cost_estimate: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class RenderResult(Model):
    artifact_ids: list[str] = Field(default_factory=list)
    provider_id: str | None = None
    model: str | None = None
    seed: int | None = None
    metrics: RenderMetrics = Field(default_factory=RenderMetrics)
    warnings: list[str] = Field(default_factory=list)


class JobError(Model):
    code: str
    message: str
    retryable: bool = True


class StateChange(Model):
    from_state: JobState
    to_state: JobState
    at: datetime
    reason: str | None = None


class RenderJob(Model):
    id: str = Field(default_factory=new_id)
    project_id: str
    request: RenderRequest
    state: JobState = JobState.DRAFT
    revision: int = Field(default=1, ge=1)
    parent_job_id: str | None = None  # input lineage: edit / upscale of that job
    retry_of: str | None = None  # retry lineage: the job this one replaces
    provider_id: str | None = None
    provider_job_id: str | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    stage: str | None = None
    result: RenderResult | None = None
    error: JobError | None = None
    history: list[StateChange] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
