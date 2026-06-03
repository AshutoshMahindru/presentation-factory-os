from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from psycopg.rows import dict_row

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool


# Status values for financial_model_specs. The lifecycle is:
#   draft -> compiled -> validated -> promoted
#                     \-> failed (terminal until manually re-opened)
# Any non-active state can transition to 'superseded' or 'archived'
# (also terminal; no resurrection).
VALID_SPEC_STATUSES: frozenset[str] = frozenset(
    {"draft", "compiled", "validated", "failed", "promoted", "superseded", "archived"}
)
ACTIVE_SPEC_STATUSES: frozenset[str] = frozenset({"draft", "compiled", "validated"})

VALID_SCENARIO_STATUSES: frozenset[str] = frozenset({"draft", "active", "archived"})


@dataclass(frozen=True)
class FinancialSpecRow:
    id: UUID
    project_id: UUID
    thesis_pillar_id: UUID | None
    name: str
    spec_json: dict[str, Any]
    status: str
    validation_errors: list[dict[str, Any]]
    promoted_to: dict[str, Any] | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class FinancialScenarioRow:
    id: UUID
    spec_id: UUID
    name: str
    scenario_json: dict[str, Any]
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class FinancialSpecPromotionResult:
    spec_id: UUID
    promoted_to: dict[str, Any]
    cell_refs: tuple[str, ...]


def _validate_status(status: str, allowed: frozenset[str], kind: str) -> None:
    if status not in allowed:
        raise ValueError(
            f"Unsupported {kind} status {status!r}; expected one of {sorted(allowed)}"
        )


class FinancialSpecRepository:
    """Sandbox CRUD for financial_model_specs and financial_scenarios.

    Step 138: the sandbox is where the FinancialAgent (step 140) drafts,
    compiles, and validates financial specs. Promotion to canonical
    (step 142) writes to a different table via a separate handler — this
    repository is sandbox-only.

    Database invariants enforced here (in addition to the schema's CHECK
    constraints and partial unique index):
      - Only one active (draft/compiled/validated) spec per pillar.
      - Status transitions are explicit (the caller picks the next state).
      - promoted_to is None until status='promoted' (set by step 142).
    """

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    # ------------------------------------------------------------------
    # Specs
    # ------------------------------------------------------------------

    def create_spec(
        self,
        project_id: UUID,
        name: str,
        spec_json: dict[str, Any] | None = None,
        thesis_pillar_id: UUID | None = None,
        status: str = "draft",
    ) -> FinancialSpecRow:
        _validate_status(status, VALID_SPEC_STATUSES, "spec")
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO financial_model_specs
                        (project_id, thesis_pillar_id, name, spec_json, status)
                    VALUES (%s, %s, %s, %s::jsonb, %s)
                    RETURNING *
                    """,
                    (
                        project_id,
                        thesis_pillar_id,
                        name,
                        json.dumps(spec_json or {}),
                        status,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return self._to_spec(row)

    def get_spec(self, spec_id: UUID) -> FinancialSpecRow | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM financial_model_specs WHERE id = %s",
                    (spec_id,),
                )
                row = cur.fetchone()
                return self._to_spec(row) if row else None

    def list_specs_by_project(
        self, project_id: UUID, status: str | None = None
    ) -> list[FinancialSpecRow]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if status:
                    cur.execute(
                        "SELECT * FROM financial_model_specs WHERE project_id = %s AND status = %s ORDER BY created_at DESC",
                        (project_id, status),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM financial_model_specs WHERE project_id = %s ORDER BY created_at DESC",
                        (project_id,),
                    )
                rows = cur.fetchall()
                return [self._to_spec(r) for r in rows]

    def get_active_spec_for_pillar(
        self, thesis_pillar_id: UUID
    ) -> FinancialSpecRow | None:
        """Return the unique active sandbox spec for a pillar, if any.

        'Active' means status IN ('draft', 'compiled', 'validated').
        The partial unique index guarantees at most one such row.
        """
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM financial_model_specs
                    WHERE thesis_pillar_id = %s
                      AND status IN ('draft', 'compiled', 'validated')
                    LIMIT 1
                    """,
                    (thesis_pillar_id,),
                )
                row = cur.fetchone()
                return self._to_spec(row) if row else None

    def update_spec_json(
        self, spec_id: UUID, spec_json: dict[str, Any]
    ) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE financial_model_specs
                    SET spec_json = %s::jsonb, updated_at = now()
                    WHERE id = %s
                    """,
                    (json.dumps(spec_json), spec_id),
                )
                conn.commit()

    def set_spec_status(
        self,
        spec_id: UUID,
        status: str,
        validation_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        _validate_status(status, VALID_SPEC_STATUSES, "spec")
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                if validation_errors is not None:
                    cur.execute(
                        """
                        UPDATE financial_model_specs
                        SET status = %s,
                            validation_errors = %s::jsonb,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (status, json.dumps(validation_errors), spec_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE financial_model_specs
                        SET status = %s, updated_at = now()
                        WHERE id = %s
                        """,
                        (status, spec_id),
                    )
                conn.commit()

    def mark_promoted(
        self, spec_id: UUID, promoted_to: dict[str, Any]
    ) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE financial_model_specs
                    SET status = 'promoted',
                        promoted_to = %s::jsonb,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (json.dumps(promoted_to), spec_id),
                )
                conn.commit()

    def promote_validated_spec_to_financial_cells(
        self,
        spec_id: UUID,
        financial_repository: Any,
        *,
        compiled_cells: list[dict[str, Any]] | None = None,
    ) -> FinancialSpecPromotionResult:
        """Promote a validated sandbox spec's compiled cells to canonical cells.

        The sandbox stores the draft spec and compiled cell payload. The
        canonical FinancialRepository owns the actual cell upserts. This
        helper bridges the two repositories while preserving lineage via
        promoted_from_spec and the sandbox promoted_to payload.
        """
        from financial_model.validator import FinancialModelValidator

        spec = self.get_spec(spec_id)
        if spec is None:
            raise ValueError(f"financial spec {spec_id} was not found")
        if spec.status != "validated":
            raise ValueError(
                f"financial spec {spec_id} must be validated before promotion"
            )

        raw_cells = compiled_cells
        if raw_cells is None:
            raw_cells = spec.spec_json.get("compiled_cells")
        if not isinstance(raw_cells, list) or not raw_cells:
            raise ValueError(
                "validated financial spec must include non-empty compiled_cells"
            )

        cells: list[dict[str, Any]] = []
        for index, raw_cell in enumerate(raw_cells):
            if not isinstance(raw_cell, dict):
                raise ValueError(f"compiled_cells[{index}] must be an object")
            cell = dict(raw_cell)
            if str(cell.get("project_id")) != str(spec.project_id):
                raise ValueError(
                    f"compiled_cells[{index}] project_id does not match spec project_id"
                )
            cells.append(cell)

        FinancialModelValidator().assert_valid_cells(cells)

        cell_refs: list[str] = []
        scenarios: set[str] = set()
        for cell in cells:
            scenario = str(cell["scenario"])
            cell_ref = str(cell["cell_ref"])
            financial_repository.upsert_cell(
                project_id=spec.project_id,
                thesis_pillar_id=spec.thesis_pillar_id,
                promoted_from_spec=spec.id,
                scenario=scenario,
                cell_ref=cell_ref,
                label=str(cell["label"]),
                value=cell["value"],
                unit=cell.get("unit"),
                formula=str(cell["formula"]),
                source_refs=list(cell.get("source_refs") or []),
                ingestion_source_type=str(
                    cell.get("ingestion_source_type", "manual_compiler")
                ),
                parser_provenance=dict(cell.get("parser_provenance") or {}),
                phase_scope_version=cell.get("phase_scope_version"),
                artifact_status=str(cell.get("artifact_status", "active")),
            )
            cell_refs.append(cell_ref)
            scenarios.add(scenario)

        promoted_to = {
            "canonical_table": "financial_cells",
            "cell_count": len(cell_refs),
            "cell_refs": cell_refs,
            "scenarios": sorted(scenarios),
        }
        self.mark_promoted(spec.id, promoted_to)
        return FinancialSpecPromotionResult(
            spec_id=spec.id,
            promoted_to=promoted_to,
            cell_refs=tuple(cell_refs),
        )

    # ------------------------------------------------------------------
    # Scenarios
    # ------------------------------------------------------------------

    def create_scenario(
        self,
        spec_id: UUID,
        name: str,
        scenario_json: dict[str, Any] | None = None,
        status: str = "draft",
    ) -> FinancialScenarioRow:
        _validate_status(status, VALID_SCENARIO_STATUSES, "scenario")
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO financial_scenarios (spec_id, name, scenario_json, status)
                    VALUES (%s, %s, %s::jsonb, %s)
                    RETURNING *
                    """,
                    (spec_id, name, json.dumps(scenario_json or {}), status),
                )
                row = cur.fetchone()
                conn.commit()
                return self._to_scenario(row)

    def get_scenario(self, scenario_id: UUID) -> FinancialScenarioRow | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM financial_scenarios WHERE id = %s",
                    (scenario_id,),
                )
                row = cur.fetchone()
                return self._to_scenario(row) if row else None

    def list_scenarios_for_spec(
        self, spec_id: UUID, status: str | None = None
    ) -> list[FinancialScenarioRow]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if status:
                    cur.execute(
                        "SELECT * FROM financial_scenarios WHERE spec_id = %s AND status = %s ORDER BY created_at DESC",
                        (spec_id, status),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM financial_scenarios WHERE spec_id = %s ORDER BY created_at DESC",
                        (spec_id,),
                    )
                rows = cur.fetchall()
                return [self._to_scenario(r) for r in rows]

    def set_scenario_status(self, scenario_id: UUID, status: str) -> None:
        _validate_status(status, VALID_SCENARIO_STATUSES, "scenario")
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE financial_scenarios
                    SET status = %s, updated_at = now()
                    WHERE id = %s
                    """,
                    (status, scenario_id),
                )
                conn.commit()

    # ------------------------------------------------------------------
    # Mappers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_spec(row: dict[str, Any]) -> FinancialSpecRow:
        return FinancialSpecRow(
            id=row["id"],
            project_id=row["project_id"],
            thesis_pillar_id=row["thesis_pillar_id"],
            name=row["name"],
            spec_json=json.loads(row["spec_json"]) if row["spec_json"] else {},
            status=row["status"],
            validation_errors=(
                json.loads(row["validation_errors"])
                if row["validation_errors"]
                else []
            ),
            promoted_to=(
                json.loads(row["promoted_to"]) if row["promoted_to"] else None
            ),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _to_scenario(row: dict[str, Any]) -> FinancialScenarioRow:
        return FinancialScenarioRow(
            id=row["id"],
            spec_id=row["spec_id"],
            name=row["name"],
            scenario_json=(
                json.loads(row["scenario_json"]) if row["scenario_json"] else {}
            ),
            status=row["status"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
