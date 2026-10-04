"""Immutable artifact blobs, addressed by content checksum.

A blob is written once and never rewritten. Two records with the same bytes
share one blob. There is no API that changes an existing blob.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
import stat
from pathlib import Path
from uuid import uuid4

from ..domain.enums import ArtifactKind
from ..domain.errors import DomainError, ErrorCode
from ..domain.models import Artifact
from .layout import DataRoot

_CHUNK = 1024 * 1024


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _guess_ext(media_type: str, original_name: str | None) -> str:
    if original_name and Path(original_name).suffix:
        return Path(original_name).suffix.lower()
    return {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "application/pdf": ".pdf"}.get(
        media_type, mimetypes.guess_extension(media_type) or ""
    )


class ArtifactStore:
    def __init__(self, data_root: DataRoot) -> None:
        self._root = data_root

    def blob_path(self, artifact: Artifact) -> Path:
        d = self._root.project(artifact.project_id).artifacts / artifact.sha256[:2]
        return d / f"{artifact.sha256}{artifact.ext}"

    def put_bytes(
        self,
        project_id: str,
        data: bytes,
        *,
        kind: ArtifactKind,
        media_type: str,
        original_name: str | None = None,
    ) -> Artifact:
        artifact = Artifact(
            project_id=project_id,
            sha256=hashlib.sha256(data).hexdigest(),
            ext=_guess_ext(media_type, original_name),
            kind=kind,
            media_type=media_type,
            size_bytes=len(data),
            original_name=original_name,
        )
        self._write_blob(artifact, data)
        return artifact

    def put_file(
        self,
        project_id: str,
        src: Path,
        *,
        kind: ArtifactKind,
        media_type: str | None = None,
        original_name: str | None = None,
    ) -> Artifact:
        name = original_name or src.name
        media_type = media_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
        return self.put_bytes(project_id, src.read_bytes(), kind=kind, media_type=media_type, original_name=name)

    def read_bytes(self, artifact: Artifact) -> bytes:
        path = self.blob_path(artifact)
        if not path.is_file():
            raise DomainError(ErrorCode.ARTIFACT_NOT_FOUND, "blob is missing on disk", artifact_id=artifact.id)
        return path.read_bytes()

    def verify(self, artifact: Artifact) -> None:
        """Raise if the blob is missing or its bytes no longer match the checksum."""
        path = self.blob_path(artifact)
        if not path.is_file():
            raise DomainError(ErrorCode.ARTIFACT_NOT_FOUND, "blob is missing on disk", artifact_id=artifact.id)
        if _sha256_file(path) != artifact.sha256:
            raise DomainError(ErrorCode.ARTIFACT_CORRUPT, "blob bytes do not match checksum", artifact_id=artifact.id)

    def _write_blob(self, artifact: Artifact, data: bytes) -> None:
        target = self.blob_path(artifact)
        if target.exists():
            # Same checksum means same bytes: reuse. Anything else is corruption, never an overwrite.
            if _sha256_file(target) != artifact.sha256:
                raise DomainError(
                    ErrorCode.ARTIFACT_CORRUPT, "existing blob does not match its checksum", path=str(target)
                )
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.{uuid4().hex}.tmp")
        try:
            with tmp.open("xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        target.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
