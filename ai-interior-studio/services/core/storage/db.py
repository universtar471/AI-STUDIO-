"""SQLite persistence. Each row keeps the full model as JSON plus the columns we query on."""
from __future__ import annotations

from pathlib import Path
from typing import Generic, Iterable, TypeVar

from sqlalchemy import Column, Engine, Integer, MetaData, String, Table, Text, create_engine, event, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from ..domain.enums import JobState
from ..domain.errors import DomainError, ErrorCode
from ..domain.models import Artifact, Model, Project, RenderJob, Room, Scene, StylePack

SCHEMA_VERSION = 1
metadata = MetaData()


def _doc_table(name: str, *extra: Column) -> Table:
    return Table(
        name,
        metadata,
        Column("id", String, primary_key=True),
        Column("project_id", String, index=True, nullable=True),
        Column("created_at", String, nullable=False),
        *extra,
        Column("data", Text, nullable=False),
    )


projects_t = _doc_table("projects")
artifacts_t = _doc_table("artifacts", Column("sha256", String, index=True, nullable=False))
scenes_t = _doc_table("scenes")
rooms_t = _doc_table("rooms")
jobs_t = _doc_table(
    "jobs",
    Column("state", String, index=True, nullable=False),
    Column("parent_job_id", String, index=True, nullable=True),
    Column("retry_of", String, index=True, nullable=True),
    Column("updated_at", String, nullable=False),
)
style_packs_t = Table(
    "style_packs",
    metadata,
    Column("id", String, primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("project_id", String, index=True, nullable=True),
    Column("created_at", String, nullable=False),
    Column("data", Text, nullable=False),
)

T = TypeVar("T", bound=Model)


class _Repo(Generic[T]):
    table: Table
    model: type[T]
    label: str

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _row(self, obj: T) -> dict:
        return {
            "id": obj.id,  # type: ignore[attr-defined]
            "project_id": getattr(obj, "project_id", None),
            "created_at": obj.created_at.isoformat(),  # type: ignore[attr-defined]
            "data": obj.model_dump_json(),
        }

    def _load(self, rows: Iterable) -> list[T]:
        return [self.model.model_validate_json(r.data) for r in rows]

    def add(self, obj: T) -> T:
        """Insert. Fails with ALREADY_EXISTS if the key is taken."""
        try:
            with self._engine.begin() as conn:
                conn.execute(self.table.insert().values(**self._row(obj)))
        except IntegrityError:
            raise DomainError(ErrorCode.ALREADY_EXISTS, f"{self.label} already exists", id=obj.id) from None  # type: ignore[attr-defined]
        return obj

    def find(self, id: str) -> T | None:
        with self._engine.connect() as conn:
            rows = conn.execute(select(self.table).where(self.table.c.id == id)).all()
        return self._load(rows)[0] if rows else None

    def get(self, id: str) -> T:
        obj = self.find(id)
        if obj is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"{self.label} not found", id=id)
        return obj

    def list(self, project_id: str | None = None) -> list[T]:
        q = select(self.table).order_by(self.table.c.created_at)
        if project_id is not None:
            q = q.where(self.table.c.project_id == project_id)
        with self._engine.connect() as conn:
            return self._load(conn.execute(q).all())


class _MutableRepo(_Repo[T]):
    def save(self, obj: T) -> T:
        """Insert or update by id."""
        row = self._row(obj)
        stmt = sqlite_insert(self.table).values(**row)
        stmt = stmt.on_conflict_do_update(index_elements=["id"], set_={k: v for k, v in row.items() if k != "id"})
        with self._engine.begin() as conn:
            conn.execute(stmt)
        return obj


class ProjectRepo(_MutableRepo[Project]):
    table, model, label = projects_t, Project, "project"

    def _row(self, obj: Project) -> dict:
        return {**super()._row(obj), "project_id": obj.id}


class ArtifactRepo(_Repo[Artifact]):
    """Insert-only: there is no save()."""

    table, model, label = artifacts_t, Artifact, "artifact"

    def _row(self, obj: Artifact) -> dict:
        return {**super()._row(obj), "sha256": obj.sha256}


class SceneRepo(_MutableRepo[Scene]):
    table, model, label = scenes_t, Scene, "scene"


class RoomRepo(_MutableRepo[Room]):
    table, model, label = rooms_t, Room, "room"


class JobRepo(_MutableRepo[RenderJob]):
    table, model, label = jobs_t, RenderJob, "job"

    def _row(self, obj: RenderJob) -> dict:
        return {
            **super()._row(obj),
            "state": str(obj.state),
            "parent_job_id": obj.parent_job_id,
            "retry_of": obj.retry_of,
            "updated_at": obj.updated_at.isoformat(),
        }

    def list_by_state(self, states: Iterable[JobState]) -> list[RenderJob]:
        q = select(self.table).where(self.table.c.state.in_([str(s) for s in states])).order_by(self.table.c.created_at)
        with self._engine.connect() as conn:
            return self._load(conn.execute(q).all())

    def retries_of(self, job_id: str) -> list[RenderJob]:
        q = select(self.table).where(self.table.c.retry_of == job_id).order_by(self.table.c.created_at)
        with self._engine.connect() as conn:
            return self._load(conn.execute(q).all())

    def children_of(self, job_id: str) -> list[RenderJob]:
        q = select(self.table).where(self.table.c.parent_job_id == job_id).order_by(self.table.c.created_at)
        with self._engine.connect() as conn:
            return self._load(conn.execute(q).all())


class StylePackRepo:
    """Insert-only per (id, version)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add_version(self, pack: StylePack) -> StylePack:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    style_packs_t.insert().values(
                        id=pack.id,
                        version=pack.version,
                        project_id=pack.project_id,
                        created_at=pack.created_at.isoformat(),
                        data=pack.model_dump_json(),
                    )
                )
        except IntegrityError:
            raise DomainError(
                ErrorCode.ALREADY_EXISTS, "style pack version already exists", id=pack.id, version=pack.version
            ) from None
        return pack

    def get(self, id: str, version: int | None = None) -> StylePack:
        """A given version, or the latest when version is None."""
        q = select(style_packs_t).where(style_packs_t.c.id == id)
        q = q.where(style_packs_t.c.version == version) if version else q.order_by(style_packs_t.c.version.desc())
        with self._engine.connect() as conn:
            row = conn.execute(q.limit(1)).first()
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, "style pack not found", id=id, version=version)
        return StylePack.model_validate_json(row.data)

    def versions(self, id: str) -> list[int]:
        q = select(style_packs_t.c.version).where(style_packs_t.c.id == id).order_by(style_packs_t.c.version)
        with self._engine.connect() as conn:
            return [r.version for r in conn.execute(q).all()]

    def list_latest(self, project_id: str | None = None) -> list[StylePack]:
        q = select(style_packs_t).order_by(style_packs_t.c.id, style_packs_t.c.version)
        if project_id is not None:
            q = q.where(style_packs_t.c.project_id == project_id)
        with self._engine.connect() as conn:
            latest = {r.id: r for r in conn.execute(q).all()}
        return [StylePack.model_validate_json(r.data) for r in latest.values()]


class Database:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{path}")

        @event.listens_for(self.engine, "connect")
        def _pragmas(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            if conn.execute(text("PRAGMA user_version")).scalar() == 0:
                conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))

        self.projects = ProjectRepo(self.engine)
        self.artifacts = ArtifactRepo(self.engine)
        self.scenes = SceneRepo(self.engine)
        self.rooms = RoomRepo(self.engine)
        self.jobs = JobRepo(self.engine)
        self.style_packs = StylePackRepo(self.engine)

    @property
    def schema_version(self) -> int:
        with self.engine.connect() as conn:
            return int(conn.execute(text("PRAGMA user_version")).scalar() or 0)

    def close(self) -> None:
        self.engine.dispose()
