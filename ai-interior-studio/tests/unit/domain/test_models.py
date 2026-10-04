from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.core.domain import (
    ROLE_DEFAULT_PRIORITY,
    ImageProvider,
    JobProgressEvent,
    ProviderCapabilities,
    ProviderHealth,
    ProviderJob,
    ProviderJobState,
    ProviderOutput,
    ProviderStatus,
    ReferenceRole,
    ReferenceSlot,
    RenderMode,
    RenderRequest,
    StylePack,
    ValidationResult,
    new_job,
)

SPEC_EXAMPLE = {  # spec section 7.1
    "project_id": "uuid",
    "mode": "sketchup_render",
    "source": {"artifact_id": "a1"},
    "camera": {"preset": "24mm", "height_mm": 1500},
    "references": [{"artifact_id": "r1", "role": "STYLE_MASTER", "priority": 100}],
    "prompt": {"style": "japandi", "materials": {}, "lighting": {}, "constraints": []},
    "quality": "preview",
    "ratio": "16:9",
    "provider_policy": "auto",
    "parent_job_id": None,
}


def test_spec_example_request_parses_and_round_trips():
    req = RenderRequest.model_validate(SPEC_EXAMPLE)
    assert RenderRequest.model_validate_json(req.model_dump_json()) == req


def test_every_role_has_a_default_priority():
    assert set(ROLE_DEFAULT_PRIORITY) == set(ReferenceRole)
    assert ReferenceSlot(artifact_id="x", role="DECOR").priority == 25
    assert ReferenceSlot(artifact_id="x", role="APPROVED_VIEW").priority == 100
    assert ReferenceSlot(artifact_id="x", role="DECOR", priority=90).priority == 90


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        RenderRequest.model_validate({**SPEC_EXAMPLE, "stepz": 4})


@pytest.mark.parametrize("mode", [RenderMode.SKETCHUP_RENDER, RenderMode.PLAN_CONCEPT])
def test_generation_needs_a_source(mode):
    with pytest.raises(ValidationError):
        RenderRequest(project_id="p", mode=mode)


@pytest.mark.parametrize("mode", [RenderMode.UPSCALE, RenderMode.IMAGE_EDIT])
def test_upscale_and_edit_need_a_parent_or_artifact(mode):
    with pytest.raises(ValidationError):
        RenderRequest(project_id="p", mode=mode)
    assert RenderRequest(project_id="p", mode=mode, parent_job_id="j1").parent_job_id == "j1"


def test_models_are_frozen(request_):
    with pytest.raises(ValidationError):
        request_.ratio = "4:3"


def test_style_pack_next_version_leaves_the_old_one_alone():
    v1 = StylePack(name="Modern Warm 01")
    v2 = v1.next_version(palette=["#C8B8A6"])
    assert (v1.version, v1.palette) == (1, [])
    assert (v2.id, v2.version, v2.palette) == (v1.id, 2, ["#C8B8A6"])


def test_progress_event_matches_spec_shape(request_):
    event = JobProgressEvent.from_job(new_job(request_), message="hi", metrics={"vram_mb": 10342})
    assert set(event.model_dump()) == {"type", "job_id", "state", "progress", "stage", "message", "metrics"}
    assert event.type == "job.progress"


def test_a_class_with_the_six_methods_is_an_image_provider():
    class Dummy:
        id = "dummy"
        capabilities = ProviderCapabilities(supported_modes=[RenderMode.SKETCHUP_RENDER])

        async def health(self) -> ProviderHealth: ...
        async def validate(self, request: RenderRequest) -> ValidationResult: ...
        async def submit(self, request: RenderRequest) -> ProviderJob: ...
        async def poll(self, provider_job_id: str) -> ProviderStatus: ...
        async def cancel(self, provider_job_id: str) -> None: ...
        async def fetch_result(self, provider_job_id: str) -> list[ProviderOutput]: ...

    assert isinstance(Dummy(), ImageProvider)
    assert not isinstance(object(), ImageProvider)
    assert ProviderStatus(state=ProviderJobState.RUNNING, progress=0.63).progress == 0.63
