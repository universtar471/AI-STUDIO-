from __future__ import annotations

import pytest

from services.core.domain import (
    ArtifactKind,
    CameraMeta,
    DomainError,
    ErrorCode,
    IN_FLIGHT_STATES,
    JobState as S,
    Project,
    Reference,
    RenderResult,
    Room,
    Scene,
    StylePack,
    new_job,
    retry_job,
    transition,
)
from services.core.storage import ArtifactStore, Database


def test_schema_version_is_set(db):
    assert db.schema_version == 1


def test_project_round_trip_and_update(db):
    p = db.projects.add(Project(name="Căn hộ Thảo Điền"))
    assert db.projects.get(p.id) == p
    db.projects.save(p.model_copy(update={"archived": True}))
    assert db.projects.get(p.id).archived is True
    assert len(db.projects.list()) == 1


def test_not_found_and_duplicate_have_codes(db):
    with pytest.raises(DomainError) as exc:
        db.projects.get("nope")
    assert exc.value.code is ErrorCode.NOT_FOUND
    p = db.projects.add(Project(name="A"))
    with pytest.raises(DomainError) as exc:
        db.projects.add(p)
    assert exc.value.code is ErrorCode.ALREADY_EXISTS


def test_artifact_records_are_insert_only(db, data_root):
    art = ArtifactStore(data_root).put_bytes("p1", b"img", kind=ArtifactKind.PREVIEW, media_type="image/png")
    db.artifacts.add(art)
    assert db.artifacts.get(art.id) == art
    assert not hasattr(db.artifacts, "save")
    with pytest.raises(DomainError) as exc:
        db.artifacts.add(art.model_copy(update={"kind": ArtifactKind.FINAL}))
    assert exc.value.code is ErrorCode.ALREADY_EXISTS
    assert db.artifacts.get(art.id).kind is ArtifactKind.PREVIEW
    assert [a.id for a in db.artifacts.list("p1")] == [art.id] and db.artifacts.list("other") == []


def test_scene_and_room_round_trip(db):
    cam = CameraMeta(eye=(0, 0, 1500), target=(4000, 0, 1200), aspect_ratio="16:9", viewport_width=1920, viewport_height=1080)
    scene = db.scenes.add(Scene(project_id="p1", name="Scene 05", rgb_artifact_id="a1", camera=cam))
    room = db.rooms.add(Room(project_id="p1", name="Master", room_type="master_bedroom", crop_artifact_id="a2", width_mm=4300, length_mm=3500))
    assert db.scenes.get(scene.id) == scene and db.rooms.get(room.id) == room


def test_style_pack_versions_are_kept(db):
    v1 = db.style_packs.add_version(
        StylePack(name="Modern Warm 01", project_id="p1", references=[Reference(artifact_id="a1", role="STYLE_MASTER")])
    )
    v2 = db.style_packs.add_version(v1.next_version(references=[*v1.references, Reference(artifact_id="a2", role="FLOOR")]))
    assert db.style_packs.versions(v1.id) == [1, 2]
    assert db.style_packs.get(v1.id) == v2  # latest by default
    assert db.style_packs.get(v1.id, 1) == v1  # old version still opens
    assert [p.version for p in db.style_packs.list_latest("p1")] == [2]
    with pytest.raises(DomainError) as exc:
        db.style_packs.add_version(v2)
    assert exc.value.code is ErrorCode.ALREADY_EXISTS


def test_job_lifecycle_persists(db, request_):
    job = db.jobs.save(new_job(request_))
    for state in (S.QUEUED, S.RUNNING):
        job = db.jobs.save(transition(job, state))
    assert [j.id for j in db.jobs.list_by_state(IN_FLIGHT_STATES)] == [job.id]
    job = db.jobs.save(transition(job, S.REVIEW, result=RenderResult(artifact_ids=["a9"])))
    assert db.jobs.list_by_state(IN_FLIGHT_STATES) == []
    closed, child = retry_job(job)
    db.jobs.save(closed)
    db.jobs.save(child)
    assert db.jobs.get(job.id).state is S.RETRY
    assert db.jobs.get(job.id).result.artifact_ids == ["a9"]  # old result is kept
    assert [j.id for j in db.jobs.retries_of(job.id)] == [child.id]
    assert len(db.jobs.list("p1")) == 2


def test_data_survives_reopening_the_database(data_root, request_):
    first = Database(data_root.db_path)
    job = first.jobs.save(transition(new_job(request_), S.QUEUED))
    first.close()
    second = Database(data_root.db_path)
    assert second.jobs.get(job.id) == job
    assert [j.id for j in second.jobs.list_by_state(IN_FLIGHT_STATES)] == [job.id]
    second.close()
