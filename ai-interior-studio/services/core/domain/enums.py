from __future__ import annotations

from enum import StrEnum


class ProjectType(StrEnum):
    APARTMENT = "apartment"
    HOUSE = "house"
    OFFICE = "office"
    RETAIL = "retail"


class RenderMode(StrEnum):
    SKETCHUP_RENDER = "sketchup_render"
    PLAN_CONCEPT = "plan_concept"
    IMAGE_EDIT = "image_edit"
    UPSCALE = "upscale"


class Quality(StrEnum):
    DRAFT = "draft"
    PREVIEW = "preview"
    FINAL = "final"


class ProviderPolicy(StrEnum):
    AUTO = "auto"
    LOCAL_ONLY = "local_only"
    CLOUD_ONLY = "cloud_only"


class ArtifactKind(StrEnum):
    SOURCE_SCENE = "source_scene"
    SCENE_PASS = "scene_pass"
    PLAN = "plan"
    ROOM_CROP = "room_crop"
    REFERENCE = "reference"
    PREVIEW = "preview"
    FINAL = "final"
    OTHER = "other"


class ReferenceRole(StrEnum):
    BASE_PLAN = "BASE_PLAN"
    STYLE_MASTER = "STYLE_MASTER"
    APPROVED_VIEW = "APPROVED_VIEW"
    CEILING = "CEILING"
    WALL = "WALL"
    FLOOR = "FLOOR"
    CABINET = "CABINET"
    FURNITURE = "FURNITURE"
    LIGHTING = "LIGHTING"
    DECOR = "DECOR"


# Spec section 2.4: P0 = 100, P1 = 75, P2 = 50, P3 = 25.
ROLE_DEFAULT_PRIORITY: dict[ReferenceRole, int] = {
    ReferenceRole.BASE_PLAN: 100,
    ReferenceRole.STYLE_MASTER: 100,
    ReferenceRole.APPROVED_VIEW: 100,
    ReferenceRole.CEILING: 75,
    ReferenceRole.WALL: 75,
    ReferenceRole.FLOOR: 75,
    ReferenceRole.CABINET: 75,
    ReferenceRole.FURNITURE: 50,
    ReferenceRole.LIGHTING: 50,
    ReferenceRole.DECOR: 25,
}


class JobState(StrEnum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    REVIEW = "REVIEW"
    RETRY = "RETRY"
    APPROVED = "APPROVED"
    FINALIZING = "FINALIZING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
