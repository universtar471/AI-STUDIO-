from __future__ import annotations

import os
import stat

import pytest

from services.core.domain import ArtifactKind, DomainError, ErrorCode
from services.core.storage import ArtifactStore, JobFiles

PNG = b"\x89PNG fake image bytes"


@pytest.fixture
def store(data_root) -> ArtifactStore:
    return ArtifactStore(data_root)


def _put(store, data=PNG, name="scene_001_rgb.png"):
    return store.put_bytes("p1", data, kind=ArtifactKind.PREVIEW, media_type="image/png", original_name=name)


def test_put_and_read_back(store):
    art = _put(store)
    assert store.read_bytes(art) == PNG
    assert (art.size_bytes, art.ext, len(art.sha256)) == (len(PNG), ".png", 64)
    store.verify(art)


def test_same_bytes_share_one_blob_and_it_is_not_rewritten(store):
    a = _put(store)
    path = store.blob_path(a)
    before = path.stat().st_mtime_ns
    b = _put(store)
    assert a.id != b.id and a.sha256 == b.sha256
    assert store.blob_path(b) == path and path.stat().st_mtime_ns == before
    assert len(list(path.parent.iterdir())) == 1


def test_different_bytes_never_touch_an_existing_blob(store):
    a = _put(store)
    b = _put(store, data=PNG + b"!")
    assert store.blob_path(a) != store.blob_path(b)
    assert store.read_bytes(a) == PNG


def test_blob_is_read_only_on_disk(store):
    mode = store.blob_path(_put(store)).stat().st_mode
    assert not mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)


def test_tampering_is_detected_and_never_silently_repaired(store):
    art = _put(store)
    path = store.blob_path(art)
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    path.write_bytes(b"tampered")
    with pytest.raises(DomainError) as exc:
        store.verify(art)
    assert exc.value.code is ErrorCode.ARTIFACT_CORRUPT
    with pytest.raises(DomainError) as exc:
        _put(store)  # same content again must not overwrite the damaged file
    assert exc.value.code is ErrorCode.ARTIFACT_CORRUPT
    assert path.read_bytes() == b"tampered"


def test_missing_blob(store):
    art = _put(store)
    path = store.blob_path(art)
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    path.unlink()
    for call in (store.verify, store.read_bytes):
        with pytest.raises(DomainError) as exc:
            call(art)
        assert exc.value.code is ErrorCode.ARTIFACT_NOT_FOUND


def test_put_file(store, tmp_path):
    src = tmp_path / "plan.pdf"
    src.write_bytes(b"%PDF-1.7")
    art = store.put_file("p1", src, kind=ArtifactKind.PLAN)
    assert (art.media_type, art.ext, art.original_name) == ("application/pdf", ".pdf", "plan.pdf")


def test_no_temp_files_left_behind(store):
    path = store.blob_path(_put(store))
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_job_snapshot_is_written_once(data_root, request_):
    files = JobFiles(data_root)
    files.write_once("p1", "j1", "request.json", request_)
    assert files.read_json("p1", "j1", "request.json")["project_id"] == "p1"
    with pytest.raises(DomainError) as exc:
        files.write_once("p1", "j1", "request.json", {"changed": True})
    assert exc.value.code is ErrorCode.SNAPSHOT_EXISTS
    assert "changed" not in files.read_text("p1", "j1", "request.json")


def test_job_snapshot_names_are_fixed(data_root):
    files = JobFiles(data_root)
    files.write_once("p1", "j1", "prompt.txt", "warm japandi living room")
    with pytest.raises(DomainError) as exc:
        files.write_once("p1", "j1", "../escape.json", {})
    assert exc.value.code is ErrorCode.SNAPSHOT_NAME_INVALID
