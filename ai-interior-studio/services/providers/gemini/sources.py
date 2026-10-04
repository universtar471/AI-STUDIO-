"""ImageSource backed by the project database and artifact store (read-only)."""
from __future__ import annotations

from services.core.domain import RenderRequest
from services.core.storage import ArtifactStore, Database


class StorageImageSource:
    def __init__(self, db: Database, store: ArtifactStore):
        self.db, self.store = db, store

    def image(self, artifact_id: str) -> tuple[bytes, str]:
        artifact = self.db.artifacts.get(artifact_id)
        self.store.verify(artifact)
        return self.store.read_bytes(artifact), artifact.media_type

    def base_image(self, request: RenderRequest) -> tuple[str, bytes, str]:
        source = request.source
        if source.artifact_id:
            artifact_id = source.artifact_id
        elif source.scene_id:
            artifact_id = self.db.scenes.get(source.scene_id).rgb_artifact_id
        elif source.room_id:
            artifact_id = self.db.rooms.get(source.room_id).crop_artifact_id
        elif request.parent_job_id:
            artifact_id = self.db.jobs.get(request.parent_job_id).result.artifact_ids[0]
        else:
            raise ValueError('Request has no base image')
        return (artifact_id, *self.image(artifact_id))
