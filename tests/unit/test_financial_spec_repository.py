from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from system.financial_spec_repository import (
    ACTIVE_SPEC_STATUSES,
    VALID_SCENARIO_STATUSES,
    VALID_SPEC_STATUSES,
    FinancialScenarioRow,
    FinancialSpecRepository,
    FinancialSpecRow,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, store: "_FakeStore", conn: "_FakeConn") -> None:
        self._store = store
        self._conn = conn
        self._result: list[dict[str, Any]] = []
        self.executed: list[tuple[str, tuple]] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))
        sql_norm = " ".join(sql.split())

        # INSERT INTO financial_model_specs
        if "INSERT INTO financial_model_specs" in sql_norm:
            (
                project_id,
                thesis_pillar_id,
                name,
                spec_json,
                status,
            ) = params
            # Enforce the partial-unique-active-per-pillar constraint.
            if (
                thesis_pillar_id is not None
                and status in ("draft", "compiled", "validated")
            ):
                for row in self._store.specs.values():
                    if (
                        row["thesis_pillar_id"] == thesis_pillar_id
                        and row["status"] in ("draft", "compiled", "validated")
                    ):
                        raise RuntimeError(
                            f"duplicate key value violates unique constraint "
                            f"uq_financial_model_specs_active_per_pillar"
                        )
            spec_id = uuid.uuid4()
            row = {
                "id": spec_id,
                "project_id": project_id,
                "thesis_pillar_id": thesis_pillar_id,
                "name": name,
                "spec_json": spec_json,
                "status": status,
                "validation_errors": json.dumps([]),
                "promoted_to": None,
                "created_at": "2026-06-02T00:00:00Z",
                "updated_at": "2026-06-02T00:00:00Z",
            }
            self._store.specs[spec_id] = row
            self._result = [row]
            return

        # SELECT * FROM financial_model_specs WHERE id = %s
        if "SELECT * FROM financial_model_specs WHERE id =" in sql_norm:
            (spec_id,) = params
            row = self._store.specs.get(spec_id)
            self._result = [dict(row)] if row else []
            return

        # SELECT * FROM financial_model_specs WHERE project_id
        if "SELECT * FROM financial_model_specs WHERE project_id" in sql_norm:
            project_id = params[0]
            if len(params) == 2 and "AND status" in sql_norm:
                status = params[1]
                rows = [
                    dict(r)
                    for r in self._store.specs.values()
                    if r["project_id"] == project_id and r["status"] == status
                ]
            else:
                rows = [
                    dict(r)
                    for r in self._store.specs.values()
                    if r["project_id"] == project_id
                ]
            self._result = rows
            return

        # SELECT active for pillar
        if (
            "SELECT * FROM financial_model_specs"
            in sql_norm
            and "thesis_pillar_id = %s" in sql_norm
            and "status IN ('draft', 'compiled', 'validated')" in sql_norm
        ):
            (pillar_id,) = params
            for row in self._store.specs.values():
                if (
                    row["thesis_pillar_id"] == pillar_id
                    and row["status"] in ("draft", "compiled", "validated")
                ):
                    self._result = [dict(row)]
                    return
            self._result = []
            return

        # UPDATE spec_json
        if "UPDATE financial_model_specs" in sql_norm and "spec_json" in sql_norm:
            spec_json, spec_id = params
            row = self._store.specs.get(spec_id)
            if row is not None:
                row["spec_json"] = spec_json
                row["updated_at"] = "2026-06-02T00:01:00Z"
            self._result = []
            return

        # UPDATE status (with or without validation_errors)
        if "UPDATE financial_model_specs" in sql_norm and "status = %s" in sql_norm:
            if "validation_errors" in sql_norm:
                status, validation_errors, spec_id = params
                row = self._store.specs.get(spec_id)
                if row is not None:
                    row["status"] = status
                    row["validation_errors"] = validation_errors
                    row["updated_at"] = "2026-06-02T00:02:00Z"
                self._result = []
                return
            status, spec_id = params
            row = self._store.specs.get(spec_id)
            if row is not None:
                row["status"] = status
                row["updated_at"] = "2026-06-02T00:04:00Z"
            self._result = []
            return

        # mark_promoted uses status = 'promoted' as a SQL literal (not a param)
        if (
            "UPDATE financial_model_specs" in sql_norm
            and "status = 'promoted'" in sql_norm
            and "promoted_to" in sql_norm
        ):
            promoted_to, spec_id = params
            row = self._store.specs.get(spec_id)
            if row is not None:
                row["status"] = "promoted"
                row["promoted_to"] = promoted_to
                row["updated_at"] = "2026-06-02T00:03:00Z"
            self._result = []
            return

        # INSERT INTO financial_scenarios
        if "INSERT INTO financial_scenarios" in sql_norm:
            spec_id, name, scenario_json, status = params
            # Enforce UNIQUE(spec_id, name)
            for row in self._store.scenarios.values():
                if row["spec_id"] == spec_id and row["name"] == name:
                    raise RuntimeError(
                        f"duplicate key value violates unique constraint "
                        f"financial_scenarios_spec_id_name_key"
                    )
            scenario_id = uuid.uuid4()
            row = {
                "id": scenario_id,
                "spec_id": spec_id,
                "name": name,
                "scenario_json": scenario_json,
                "status": status,
                "created_at": "2026-06-02T00:00:00Z",
                "updated_at": "2026-06-02T00:00:00Z",
            }
            self._store.scenarios[scenario_id] = row
            self._result = [row]
            return

        # SELECT scenario by id
        if "SELECT * FROM financial_scenarios WHERE id =" in sql_norm:
            (scenario_id,) = params
            row = self._store.scenarios.get(scenario_id)
            self._result = [dict(row)] if row else []
            return

        # SELECT scenarios for spec
        if "SELECT * FROM financial_scenarios WHERE spec_id" in sql_norm:
            spec_id = params[0]
            if len(params) == 2 and "AND status" in sql_norm:
                status = params[1]
                rows = [
                    dict(r)
                    for r in self._store.scenarios.values()
                    if r["spec_id"] == spec_id and r["status"] == status
                ]
            else:
                rows = [
                    dict(r)
                    for r in self._store.scenarios.values()
                    if r["spec_id"] == spec_id
                ]
            self._result = rows
            return

        # UPDATE financial_scenarios status
        if "UPDATE financial_scenarios" in sql_norm and "status = %s" in sql_norm:
            status, scenario_id = params
            row = self._store.scenarios.get(scenario_id)
            if row is not None:
                row["status"] = status
                row["updated_at"] = "2026-06-02T00:05:00Z"
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
        # spec_id -> row dict
        self.specs: dict[uuid.UUID, dict[str, Any]] = {}
        # scenario_id -> row dict
        self.scenarios: dict[uuid.UUID, dict[str, Any]] = {}


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


class _RecordingFinancialRepository:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

    def upsert_cell(self, **kwargs: Any) -> object:
        self.upserts.append(kwargs)
        return object()


# ---------------------------------------------------------------------------
# Specs: create / get / list
# ---------------------------------------------------------------------------


def test_create_spec_returns_row_with_defaults() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()

    row = repo.create_spec(
        project_id=project_id,
        name="Bull case revenue model",
        spec_json={"revenue_growth": 0.15},
    )

    assert isinstance(row, FinancialSpecRow)
    assert row.project_id == project_id
    assert row.thesis_pillar_id is None
    assert row.name == "Bull case revenue model"
    assert row.spec_json == {"revenue_growth": 0.15}
    assert row.status == "draft"
    assert row.validation_errors == []
    assert row.promoted_to is None
    assert pool.last_conn is not None
    assert pool.last_conn.committed is True


def test_create_spec_with_pillar_linkage() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    pillar_id = uuid.uuid4()

    row = repo.create_spec(
        project_id=project_id,
        name="Pillar-backed model",
        thesis_pillar_id=pillar_id,
    )

    assert row.thesis_pillar_id == pillar_id


def test_create_spec_rejects_unknown_status() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported spec status"):
        repo.create_spec(
            project_id=uuid.uuid4(),
            name="bad",
            status="exploded",
        )


def test_get_spec_returns_none_for_unknown_id() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    assert repo.get_spec(uuid.uuid4()) is None


def test_list_specs_by_project_filters_by_status() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    other_project = uuid.uuid4()
    a = repo.create_spec(project_id=project_id, name="A", status="draft")
    b = repo.create_spec(project_id=project_id, name="B", status="compiled")
    repo.create_spec(project_id=other_project, name="other")
    repo.create_spec(project_id=project_id, name="C", status="draft")

    all_rows = repo.list_specs_by_project(project_id)
    assert {r.id for r in all_rows} == {a.id, b.id, all_rows[2].id if len(all_rows) > 2 else b.id}
    # Sanity: not in other project
    assert all(r.project_id == project_id for r in all_rows)

    drafts = repo.list_specs_by_project(project_id, status="draft")
    assert {r.id for r in drafts} == {a.id, [r.id for r in all_rows if r.name == "C"][0]}


# ---------------------------------------------------------------------------
# Active-per-pillar invariant
# ---------------------------------------------------------------------------


def test_get_active_spec_for_pillar_returns_active_row() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    pillar_id = uuid.uuid4()
    spec = repo.create_spec(
        project_id=project_id,
        name="active",
        thesis_pillar_id=pillar_id,
        status="compiled",
    )
    result = repo.get_active_spec_for_pillar(pillar_id)
    assert result is not None
    assert result.id == spec.id


def test_create_spec_rejects_second_active_for_same_pillar() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    pillar_id = uuid.uuid4()
    repo.create_spec(
        project_id=project_id,
        name="first",
        thesis_pillar_id=pillar_id,
        status="draft",
    )
    with pytest.raises(RuntimeError, match="uq_financial_model_specs_active_per_pillar"):
        repo.create_spec(
            project_id=project_id,
            name="second",
            thesis_pillar_id=pillar_id,
            status="draft",
        )


def test_failed_spec_does_not_block_new_active_for_same_pillar() -> None:
    """Once status moves out of ACTIVE_SPEC_STATUSES, the slot frees up."""
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    pillar_id = uuid.uuid4()
    first = repo.create_spec(
        project_id=project_id,
        name="first",
        thesis_pillar_id=pillar_id,
        status="draft",
    )
    repo.set_spec_status(first.id, "failed")
    # Now a second active spec for the same pillar must succeed.
    second = repo.create_spec(
        project_id=project_id,
        name="second",
        thesis_pillar_id=pillar_id,
        status="draft",
    )
    assert second.thesis_pillar_id == pillar_id
    assert second.status == "draft"


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


def test_set_spec_status_updates_status() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    spec = repo.create_spec(project_id=uuid.uuid4(), name="x")
    repo.set_spec_status(spec.id, "compiled")
    refreshed = repo.get_spec(spec.id)
    assert refreshed is not None
    assert refreshed.status == "compiled"


def test_set_spec_status_records_validation_errors() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    spec = repo.create_spec(project_id=uuid.uuid4(), name="x")
    errors = [{"path": "$.revenue", "message": "must be number"}]
    repo.set_spec_status(spec.id, "failed", validation_errors=errors)
    refreshed = repo.get_spec(spec.id)
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert refreshed.validation_errors == errors


def test_mark_promoted_records_promoted_to_payload() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    spec = repo.create_spec(project_id=uuid.uuid4(), name="x")
    payload = {"canonical_table": "financial_models", "promoted_at": "2026-06-02T00:00:00Z"}
    repo.mark_promoted(spec.id, payload)
    refreshed = repo.get_spec(spec.id)
    assert refreshed is not None
    assert refreshed.status == "promoted"
    assert refreshed.promoted_to == payload


# ---------------------------------------------------------------------------
# Step 142 promotion bridge
# ---------------------------------------------------------------------------


def test_promote_validated_spec_to_financial_cells_upserts_and_marks_promoted() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    pillar_id = uuid.uuid4()
    spec = repo.create_spec(
        project_id=project_id,
        name="Validated sandbox model",
        thesis_pillar_id=pillar_id,
        status="validated",
        spec_json={
            "compiled_cells": [
                {
                    "project_id": str(project_id),
                    "scenario": "base",
                    "cell_ref": "Revenue",
                    "label": "Revenue",
                    "value": 1000,
                    "unit": "USD",
                    "formula": "1000",
                    "source_refs": ["src-1"],
                    "ingestion_source_type": "manual_compiler",
                    "parser_provenance": {"parser_name": "pfos_spec_compiler"},
                    "phase_scope_version": 3,
                },
                {
                    "project_id": str(project_id),
                    "scenario": "downside",
                    "cell_ref": "EBITDA",
                    "label": "EBITDA",
                    "value": 250,
                    "formula": "Revenue - opex",
                },
            ],
        },
    )
    canonical_repo = _RecordingFinancialRepository()

    result = repo.promote_validated_spec_to_financial_cells(
        spec.id,
        canonical_repo,
    )

    assert result.spec_id == spec.id
    assert result.cell_refs == ("Revenue", "EBITDA")
    assert result.promoted_to == {
        "canonical_table": "financial_cells",
        "cell_count": 2,
        "cell_refs": ["Revenue", "EBITDA"],
        "scenarios": ["base", "downside"],
    }

    refreshed = repo.get_spec(spec.id)
    assert refreshed is not None
    assert refreshed.status == "promoted"
    assert refreshed.promoted_to == result.promoted_to

    assert len(canonical_repo.upserts) == 2
    revenue, ebitda = canonical_repo.upserts
    assert revenue["project_id"] == project_id
    assert revenue["thesis_pillar_id"] == pillar_id
    assert revenue["promoted_from_spec"] == spec.id
    assert revenue["scenario"] == "base"
    assert revenue["cell_ref"] == "Revenue"
    assert revenue["source_refs"] == ["src-1"]
    assert revenue["ingestion_source_type"] == "manual_compiler"
    assert revenue["parser_provenance"] == {"parser_name": "pfos_spec_compiler"}
    assert revenue["phase_scope_version"] == 3
    assert revenue["artifact_status"] == "active"
    assert ebitda["scenario"] == "downside"
    assert ebitda["cell_ref"] == "EBITDA"
    assert ebitda["source_refs"] == []
    assert ebitda["parser_provenance"] == {}


def test_promote_validated_spec_rejects_project_mismatch_before_upsert() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    project_id = uuid.uuid4()
    spec = repo.create_spec(
        project_id=project_id,
        name="Mismatched sandbox model",
        status="validated",
        spec_json={
            "compiled_cells": [
                {
                    "project_id": str(uuid.uuid4()),
                    "scenario": "base",
                    "cell_ref": "Revenue",
                    "label": "Revenue",
                    "value": 1000,
                    "formula": "1000",
                }
            ],
        },
    )
    canonical_repo = _RecordingFinancialRepository()

    with pytest.raises(ValueError, match="project_id does not match spec project_id"):
        repo.promote_validated_spec_to_financial_cells(spec.id, canonical_repo)

    assert canonical_repo.upserts == []
    refreshed = repo.get_spec(spec.id)
    assert refreshed is not None
    assert refreshed.status == "validated"
    assert refreshed.promoted_to is None


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def test_create_scenario_returns_row() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    spec = repo.create_spec(project_id=uuid.uuid4(), name="x")
    scenario = repo.create_scenario(
        spec_id=spec.id,
        name="base",
        scenario_json={"growth": 0.1},
    )
    assert isinstance(scenario, FinancialScenarioRow)
    assert scenario.spec_id == spec.id
    assert scenario.name == "base"
    assert scenario.scenario_json == {"growth": 0.1}
    assert scenario.status == "draft"


def test_create_scenario_rejects_unknown_status() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    spec = repo.create_spec(project_id=uuid.uuid4(), name="x")
    with pytest.raises(ValueError, match="Unsupported scenario status"):
        repo.create_scenario(spec_id=spec.id, name="x", status="nope")


def test_create_scenario_rejects_duplicate_name_for_same_spec() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    spec = repo.create_spec(project_id=uuid.uuid4(), name="x")
    repo.create_scenario(spec_id=spec.id, name="base")
    with pytest.raises(RuntimeError, match="financial_scenarios_spec_id_name_key"):
        repo.create_scenario(spec_id=spec.id, name="base")


def test_list_scenarios_for_spec_filters_by_status() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    spec = repo.create_spec(project_id=uuid.uuid4(), name="x")
    a = repo.create_scenario(spec_id=spec.id, name="a", status="active")
    b = repo.create_scenario(spec_id=spec.id, name="b", status="draft")
    archived = repo.create_scenario(spec_id=spec.id, name="c", status="archived")

    all_rows = repo.list_scenarios_for_spec(spec.id)
    assert {r.id for r in all_rows} == {a.id, b.id, archived.id}

    active = repo.list_scenarios_for_spec(spec.id, status="active")
    assert {r.id for r in active} == {a.id}


def test_set_scenario_status_transitions() -> None:
    pool = _FakePool()
    repo = FinancialSpecRepository(pool)  # type: ignore[arg-type]
    spec = repo.create_spec(project_id=uuid.uuid4(), name="x")
    s = repo.create_scenario(spec_id=spec.id, name="x")
    repo.set_scenario_status(s.id, "active")
    refreshed = repo.get_scenario(s.id)
    assert refreshed is not None
    assert refreshed.status == "active"


# ---------------------------------------------------------------------------
# Status enums exposed for external use
# ---------------------------------------------------------------------------


def test_status_enums_match_documented_lifecycle() -> None:
    assert "draft" in VALID_SPEC_STATUSES
    assert "compiled" in VALID_SPEC_STATUSES
    assert "validated" in VALID_SPEC_STATUSES
    assert "failed" in VALID_SPEC_STATUSES
    assert "promoted" in VALID_SPEC_STATUSES
    assert "superseded" in VALID_SPEC_STATUSES
    assert "archived" in VALID_SPEC_STATUSES

    assert ACTIVE_SPEC_STATUSES == frozenset({"draft", "compiled", "validated"})

    assert VALID_SCENARIO_STATUSES == frozenset({"draft", "active", "archived"})
