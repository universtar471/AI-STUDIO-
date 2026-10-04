"""Folder layout on disk (spec section 7)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_PROJECT_DIRS = ("sources/sketchup", "sources/plans", "artifacts", "jobs", "cache", "logs")


@dataclass(frozen=True)
class ProjectPaths:
    base: Path

    @property
    def artifacts(self) -> Path:
        return self.base / "artifacts"

    @property
    def jobs(self) -> Path:
        return self.base / "jobs"

    def job_dir(self, job_id: str) -> Path:
        return self.jobs / job_id

    def ensure(self) -> "ProjectPaths":
        for d in _PROJECT_DIRS:
            (self.base / d).mkdir(parents=True, exist_ok=True)
        return self


@dataclass(frozen=True)
class DataRoot:
    """Everything the app writes lives under one folder, outside the git repo."""

    root: Path

    @property
    def db_path(self) -> Path:
        return self.root / "studio.sqlite3"

    def project(self, project_id: str) -> ProjectPaths:
        return ProjectPaths(self.root / "projects" / project_id)
