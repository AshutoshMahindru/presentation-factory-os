from __future__ import annotations

import uuid
from typing import Any

import pytest

from system.financial_repository import FinancialRepository
from system.source_lifecycle_repository import SourceLifecycleRepository


class FakeResult:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


class _FakeCursor:
    def __init__(self, store: "_FakeStore") -> None:
        self._store = store
        self._result: list[dict[str, Any]] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        sql_norm = " ".join(sql.split())
        if "UPDATE financial_cells" not in sql_norm or "ANY(source_refs)" not in sql_norm:
            raise AssertionError(f"unexpected SQL: {sql_norm}")

        project_id, source_id = params
        rows = []
        for row in self._store.cells:
            if (
                row["project_id"] == project_id
                and row["artifact_status"] == "active"
                and source_id in row["source_refs"]
            ):
                row["artifact_status"] = "stale_due_to_retreat"
                rows.append({"id": row["id"]})
        self._result = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._result)


class _FakeConn:
    def __init__(self, store: "_FakeStore") -> None:
        self._store = store
        self.committed = False

    def cursor(self, row_factory: Any = None) -> _FakeCursor:
        return _FakeCursor(self._store)

    def commit(self) -> None:
        self.committed = True


class _FakePool:
    def __init__(self, store: "_FakeStore") -> None:
        self._store = store
        self.last_conn: _FakeConn | None = None

    def connection(self):  # type: ignore[no-untyped-def]
        outer = self

        class _CM:
            def __enter__(self_inner):  # type: ignore[no-untyped-def]
                conn = _FakeConn(outer._store)
                outer.last_conn = conn
                return conn

            def __exit__(self_inner, *exc: Any) -> bool:  # type: ignore[no-untyped-def]
                return False

        return _CM()


class _FakeStore:
    def __init__(self, project_id: uuid.UUID, other_project_id: uuid.UUID) -> None:
        self.cells = [
            {
                "id": uuid.uuid4(),
                "project_id": project_id,
                "source_refs": ["source-retracted", "source-active"],
                "artifact_status": "active",
            },
            {
                "id": uuid.uuid4(),
                "project_id": project_id,
                "source_refs": ["source-active"],
                "artifact_status": "active",
            },
            {
                "id": uuid.uuid4(),
                "project_id": project_id,
                "source_refs": ["source-retracted"],
                "artifact_status": "archived",
            },
            {
                "id": uuid.uuid4(),
                "project_id": other_project_id,
                "source_refs": ["source-retracted"],
                "artifact_status": "active",
            },
        ]


def test_retracted_source_marks_only_matching_active_financial_cells_stale() -> None:
    project_id = uuid.uuid4()
    store = _FakeStore(project_id=project_id, other_project_id=uuid.uuid4())
    repo = FinancialRepository(_FakePool(store))  # type: ignore[arg-type]

    stale_count = repo.mark_cells_stale_for_retracted_source(
        project_id=project_id,
        source_id="source-retracted",
    )

    assert stale_count == 1
    assert [row["artifact_status"] for row in store.cells] == [
        "stale_due_to_retreat",
        "active",
        "archived",
        "active",
    ]


def test_retracted_source_invalidation_rejects_blank_source_id() -> None:
    repo = FinancialRepository(_FakePool(_FakeStore(uuid.uuid4(), uuid.uuid4())))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="source_id is required"):
        repo.mark_cells_stale_for_retracted_source(uuid.uuid4(), " ")


def test_source_lifecycle_repository_exposes_psql_invalidation_lane() -> None:
    repository = SourceLifecycleRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult("2\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    result = repository.invalidate_financial_cells_for_retracted_source(
        "project-with-'quote",
        "source-with-'quote",
    )

    assert result.project_id == "project-with-'quote"
    assert result.source_id == "source-with-'quote"
    assert result.stale_financial_cells_count == 2
    assert "UPDATE financial_cells" in captured["sql"]
    assert "artifact_status = 'stale_due_to_retreat'" in captured["sql"]
    assert "project_id = 'project-with-''quote'" in captured["sql"]
    assert "'source-with-''quote' = ANY(source_refs)" in captured["sql"]
