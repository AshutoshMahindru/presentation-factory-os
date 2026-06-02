from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest

from system.financial_repository import (
    VALID_CELL_STATUSES,
    FinancialCellRow,
    FinancialRepository,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, store: "_FakeStore", conn: "_FakeConn") -> None:
        self._store = store
        self._conn = conn
        self._result: list[dict[str, Any]] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def execute(self, sql: str, params: tuple = ()) -> None:
        sql_norm = " ".join(sql.split())

        if "INSERT INTO financial_cells" in sql_norm and "ON CONFLICT" in sql_norm:
            (
                project_id,
                thesis_pillar_id,
                promoted_from_spec,
                scenario,
                cell_ref,
                label,
                value,
                unit,
                formula,
                source_refs,
                ingestion_source_type,
                parser_provenance,
                phase_scope_version,
                artifact_status,
            ) = params
            key = (project_id, scenario, cell_ref)
            existing_id = self._store.cell_keys.get(key)
            cell_id = existing_id or uuid.uuid4()
            row = {
                "id": cell_id,
                "project_id": project_id,
                "thesis_pillar_id": thesis_pillar_id,
                "promoted_from_spec": promoted_from_spec,
                "scenario": scenario,
                "cell_ref": cell_ref,
                "label": label,
                "value": value,
                "unit": unit,
                "formula": formula,
                "source_refs": list(source_refs or []),
                "ingestion_source_type": ingestion_source_type,
                "parser_provenance": parser_provenance,
                "phase_scope_version": phase_scope_version,
                "artifact_status": artifact_status,
                "created_at": self._store.now_iso(),
                "updated_at": self._store.now_iso(),
            }
            self._store.cells[cell_id] = row
            self._store.cell_keys[key] = cell_id
            self._result = [row]
            return

        if "SELECT * FROM financial_cells" in sql_norm and "cell_ref = %s" in sql_norm:
            project_id, scenario, cell_ref = params
            for row in self._store.cells.values():
                if (
                    row["project_id"] == project_id
                    and row["scenario"] == scenario
                    and row["cell_ref"] == cell_ref
                ):
                    self._result = [dict(row)]
                    return
            self._result = []
            return

        if "SELECT * FROM financial_cells" in sql_norm and "project_id = %s" in sql_norm:
            project_id = params[0]
            rows = [
                dict(r)
                for r in self._store.cells.values()
                if r["project_id"] == project_id
            ]
            # Apply scenario / status filters
            if "AND scenario = %s" in sql_norm:
                scenario = params[1]
                rows = [r for r in rows if r["scenario"] == scenario]
            if "AND artifact_status = %s" in sql_norm:
                # Could be the 2nd or 3rd param depending on scenario filter
                if "AND scenario = %s" in sql_norm:
                    status = params[2]
                else:
                    status = params[1]
                rows = [r for r in rows if r["artifact_status"] == status]
            rows.sort(key=lambda r: r["cell_ref"])
            self._result = rows
            return

        if "WHERE thesis_pillar_id = %s" in sql_norm:
            (pillar_id,) = params
            rows = sorted(
                (
                    dict(r)
                    for r in self._store.cells.values()
                    if r["thesis_pillar_id"] == pillar_id
                ),
                key=lambda r: (r["scenario"], r["cell_ref"]),
            )
            self._result = rows
            return

        if "WHERE promoted_from_spec = %s" in sql_norm:
            (spec_id,) = params
            rows = sorted(
                (
                    dict(r)
                    for r in self._store.cells.values()
                    if r["promoted_from_spec"] == spec_id
                ),
                key=lambda r: (r["scenario"], r["cell_ref"]),
            )
            self._result = rows
            return

        if "UPDATE financial_cells" in sql_norm and "artifact_status = %s" in sql_norm:
            status, project_id, scenario, cell_ref = params
            key = (project_id, scenario, cell_ref)
            cell_id = self._store.cell_keys.get(key)
            if cell_id is not None:
                self._store.cells[cell_id]["artifact_status"] = status
                self._store.cells[cell_id]["updated_at"] = self._store.now_iso()
            self._result = []
            return

        if "UPDATE financial_cells" in sql_norm and "phase_scope_version" in sql_norm:
            version, project_id, scenario, cell_ref = params
            key = (project_id, scenario, cell_ref)
            cell_id = self._store.cell_keys.get(key)
            if cell_id is not None:
                self._store.cells[cell_id]["phase_scope_version"] = version
                self._store.cells[cell_id]["updated_at"] = self._store.now_iso()
            self._result = []
            return

        raise AssertionError(f"_FakeCursor: unhandled SQL: {sql_norm[:80]}...")

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._result)

    def fetchone(self) -> dict[str, Any] | None:
        return self._result[0] if self._result else None


class _FakeConn:
    def __init__(self, store: "_FakeStore") -> None:
        self._store = store
        self.committed = False

    def cursor(self, row_factory: Any = None) -> _FakeCursor:
        return _FakeCursor(self._store, self)

    def commit(self) -> None:
        self.committed = True


class _FakeStore:
    def __init__(self) -> None:
        self.cells: dict[uuid.UUID, dict[str, Any]] = {}
        # (project_id, scenario, cell_ref) -> cell_id
        self.cell_keys: dict[tuple[uuid.UUID, str, str], uuid.UUID] = {}
        self._tick = 0

    def now_iso(self) -> str:
        self._tick += 1
        return f"2026-06-02T00:00:{self._tick:02d}Z"


class _FakePool:
    def __init__(self, store: _FakeStore | None = None) -> None:
        self._store = store or _FakeStore()
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


# ---------------------------------------------------------------------------
# Upsert + read
# ---------------------------------------------------------------------------


def test_upsert_creates_new_cell() -> None:
    pool = _FakePool()
    repo = FinancialRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    pillar_id = uuid.uuid4()
    spec_id = uuid.uuid4()

    cell = repo.upsert_cell(
        project_id=project_id,
        scenario="base",
        cell_ref="Revenue",
        label="Revenue year 1",
        value=Decimal("1150.00"),
        formula="1000 * (1 + growth_rate)",
        thesis_pillar_id=pillar_id,
        promoted_from_spec=spec_id,
        unit="USD",
        source_refs=["source-A", "source-B"],
        parser_provenance={"parser_name": "pfos_spec_compiler", "parser_version": "0.1.0"},
        phase_scope_version=2,
    )

    assert isinstance(cell, FinancialCellRow)
    assert cell.project_id == project_id
    assert cell.thesis_pillar_id == pillar_id
    assert cell.promoted_from_spec == spec_id
    assert cell.scenario == "base"
    assert cell.cell_ref == "Revenue"
    assert cell.value == Decimal("1150.00")
    assert cell.unit == "USD"
    assert cell.source_refs == ["source-A", "source-B"]
    assert cell.artifact_status == "active"
    assert pool.last_conn is not None
    assert pool.last_conn.committed is True


def test_upsert_updates_existing_cell() -> None:
    pool = _FakePool()
    repo = FinancialRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    cell_v1 = repo.upsert_cell(
        project_id=project_id,
        scenario="base",
        cell_ref="Revenue",
        label="v1",
        value=Decimal("100"),
        formula="x",
    )
    cell_v2 = repo.upsert_cell(
        project_id=project_id,
        scenario="base",
        cell_ref="Revenue",
        label="v2",
        value=Decimal("200"),
        formula="y",
    )
    # Same id (upsert), updated value/label/formula
    assert cell_v1.id == cell_v2.id
    assert cell_v2.value == Decimal("200")
    assert cell_v2.label == "v2"
    assert cell_v2.formula == "y"


def test_upsert_rejects_unknown_status() -> None:
    pool = _FakePool()
    repo = FinancialRepository(pool)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported cell artifact_status"):
        repo.upsert_cell(
            project_id=uuid.uuid4(),
            scenario="base",
            cell_ref="X",
            label="lbl",
            value=Decimal("1"),
            formula="1",
            artifact_status="pending",
        )


def test_get_cell_returns_none_when_missing() -> None:
    pool = _FakePool()
    repo = FinancialRepository(pool)  # type: ignore[arg-type]
    assert (
        repo.get_cell(uuid.uuid4(), "base", "missing") is None
    )


def test_get_cell_round_trips() -> None:
    pool = _FakePool()
    repo = FinancialRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    repo.upsert_cell(
        project_id=project_id,
        scenario="base",
        cell_ref="X",
        label="L",
        value=Decimal("42"),
        formula="1+1",
    )
    fetched = repo.get_cell(project_id, "base", "X")
    assert fetched is not None
    assert fetched.value == Decimal("42")
    assert fetched.cell_ref == "X"


def test_list_cells_by_project_filters_by_scenario_and_status() -> None:
    pool = _FakePool()
    repo = FinancialRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    a = repo.upsert_cell(
        project_id=project_id, scenario="base", cell_ref="A",
        label="a", value=Decimal("1"), formula="1",
    )
    repo.upsert_cell(
        project_id=project_id, scenario="base", cell_ref="B",
        label="b", value=Decimal("2"), formula="2",
    )
    bull = repo.upsert_cell(
        project_id=project_id, scenario="bull", cell_ref="A",
        label="a-bull", value=Decimal("3"), formula="3",
    )
    # Move A to archived
    repo.set_artifact_status(project_id, "base", "A", "archived")

    all_rows = repo.list_cells_by_project(project_id)
    assert len(all_rows) == 3
    assert {r.cell_ref for r in all_rows} == {"A", "B", "A"}
    assert {r.scenario for r in all_rows} == {"base", "base", "bull"}

    base_rows = repo.list_cells_by_project(project_id, scenario="base")
    assert {r.id for r in base_rows} == {a.id, [r for r in all_rows if r.cell_ref == "B"][0].id}

    active_base = repo.list_cells_by_project(
        project_id, scenario="base", artifact_status="active"
    )
    assert {r.id for r in active_base} == {
        r.id for r in all_rows if r.cell_ref == "B"
    }


# ---------------------------------------------------------------------------
# Pillar / spec lineage
# ---------------------------------------------------------------------------


def test_list_cells_for_pillar_returns_linked_cells() -> None:
    pool = _FakePool()
    repo = FinancialRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    pillar_a = uuid.uuid4()
    pillar_b = uuid.uuid4()
    repo.upsert_cell(
        project_id=project_id, scenario="base", cell_ref="A1",
        label="a1", value=Decimal("1"), formula="1",
        thesis_pillar_id=pillar_a,
    )
    repo.upsert_cell(
        project_id=project_id, scenario="bull", cell_ref="A2",
        label="a2", value=Decimal("2"), formula="2",
        thesis_pillar_id=pillar_a,
    )
    repo.upsert_cell(
        project_id=project_id, scenario="base", cell_ref="B1",
        label="b1", value=Decimal("3"), formula="3",
        thesis_pillar_id=pillar_b,
    )

    pillar_a_cells = repo.list_cells_for_pillar(pillar_a)
    assert {c.cell_ref for c in pillar_a_cells} == {"A1", "A2"}
    pillar_b_cells = repo.list_cells_for_pillar(pillar_b)
    assert {c.cell_ref for c in pillar_b_cells} == {"B1"}


def test_list_cells_from_spec_returns_lineage() -> None:
    pool = _FakePool()
    repo = FinancialRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    spec_a = uuid.uuid4()
    spec_b = uuid.uuid4()
    repo.upsert_cell(
        project_id=project_id, scenario="base", cell_ref="A",
        label="a", value=Decimal("1"), formula="1",
        promoted_from_spec=spec_a,
    )
    repo.upsert_cell(
        project_id=project_id, scenario="base", cell_ref="B",
        label="b", value=Decimal("2"), formula="2",
        promoted_from_spec=spec_b,
    )
    a_cells = repo.list_cells_from_spec(spec_a)
    assert {c.cell_ref for c in a_cells} == {"A"}


# ---------------------------------------------------------------------------
# Mutate
# ---------------------------------------------------------------------------


def test_set_artifact_status_transitions() -> None:
    pool = _FakePool()
    repo = FinancialRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    repo.upsert_cell(
        project_id=project_id, scenario="base", cell_ref="X",
        label="x", value=Decimal("1"), formula="1",
    )
    repo.set_artifact_status(project_id, "base", "X", "blocked")
    refreshed = repo.get_cell(project_id, "base", "X")
    assert refreshed is not None
    assert refreshed.artifact_status == "blocked"


def test_set_artifact_status_rejects_unknown() -> None:
    pool = _FakePool()
    repo = FinancialRepository(pool)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported cell artifact_status"):
        repo.set_artifact_status(uuid.uuid4(), "base", "X", "weird")


def test_set_phase_scope_version_records_value() -> None:
    pool = _FakePool()
    repo = FinancialRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    repo.upsert_cell(
        project_id=project_id, scenario="base", cell_ref="X",
        label="x", value=Decimal("1"), formula="1",
    )
    repo.set_phase_scope_version(project_id, "base", "X", 5)
    refreshed = repo.get_cell(project_id, "base", "X")
    assert refreshed is not None
    assert refreshed.phase_scope_version == 5


# ---------------------------------------------------------------------------
# Sanity: status enum
# ---------------------------------------------------------------------------


def test_valid_cell_statuses_match_schema_check() -> None:
    assert VALID_CELL_STATUSES == frozenset(
        {"active", "stale_due_to_retreat", "archived", "blocked"}
    )
