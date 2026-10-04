from __future__ import annotations

import pytest

from services.core.domain import RenderMode, RenderRequest, SourceRef
from services.core.storage import Database, DataRoot


@pytest.fixture
def data_root(tmp_path) -> DataRoot:
    return DataRoot(tmp_path / "data")


@pytest.fixture
def db(data_root) -> Database:
    database = Database(data_root.db_path)
    yield database
    database.close()


@pytest.fixture
def request_() -> RenderRequest:
    return RenderRequest(project_id="p1", mode=RenderMode.SKETCHUP_RENDER, source=SourceRef(artifact_id="a1"))
