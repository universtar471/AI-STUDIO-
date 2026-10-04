"""Per-job snapshot files (spec section 7): written once, never overwritten."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from ..domain.errors import DomainError, ErrorCode
from .layout import DataRoot

SNAPSHOT_NAMES = frozenset({"request.json", "provider_request.json", "prompt.txt", "refs.json", "metrics.json"})


class JobFiles:
    def __init__(self, data_root: DataRoot) -> None:
        self._root = data_root

    def write_once(self, project_id: str, job_id: str, name: str, payload: BaseModel | dict | list | str) -> None:
        if name not in SNAPSHOT_NAMES:
            raise DomainError(ErrorCode.SNAPSHOT_NAME_INVALID, f"unknown snapshot file {name!r}", allowed=sorted(SNAPSHOT_NAMES))
        if isinstance(payload, BaseModel):
            text = payload.model_dump_json(indent=2)
        elif isinstance(payload, str):
            text = payload
        else:
            text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        job_dir = self._root.project(project_id).job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        try:
            with (job_dir / name).open("x", encoding="utf-8") as f:
                f.write(text)
        except FileExistsError:
            raise DomainError(ErrorCode.SNAPSHOT_EXISTS, f"{name} already written for this job", job_id=job_id) from None

    def read_text(self, project_id: str, job_id: str, name: str) -> str:
        path = self._root.project(project_id).job_dir(job_id) / name
        if not path.is_file():
            raise DomainError(ErrorCode.NOT_FOUND, f"{name} not found", job_id=job_id)
        return path.read_text(encoding="utf-8")

    def read_json(self, project_id: str, job_id: str, name: str) -> Any:
        return json.loads(self.read_text(project_id, job_id, name))
