from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from psycopg.rows import dict_row

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool


# Allowed artifact_status values (must match the schema CHECK constraint).
VALID_CELL_STATUSES: frozenset[str] = frozenset(
    {"active", "stale_due_to_retreat", "archived", "blocked"}
)


@dataclass(frozen=True)
class FinancialCellRow:
    """Canonical financial cell. Distinct from the sandbox spec.

    The sandbox spec (system.financial_spec_repository.FinancialSpecRow)
    holds the formula and metadata being drafted. The canonical cell
    holds the evaluated numeric value plus its promotion lineage.
    """

    id: UUID
    project_id: UUID
    thesis_pillar_id: UUID | None
    promoted_from_spec: UUID | None
    scenario: str
    cell_ref: str
    label: str
    value: Decimal
    unit: str | None
    formula: str
    source_refs: list[str]
    ingestion_source_type: str
    parser_provenance: dict[str, Any]
    phase_scope_version: int | None
    artifact_status: str
    created_at: str
    updated_at: str


def _validate_status(status: str) -> None:
    if status not in VALID_CELL_STATUSES:
        raise ValueError(
            f"Unsupported cell artifact_status {status!r}; "
            f"expected one of {sorted(VALID_CELL_STATUSES)}"
        )


class FinancialRepository:
    """CRUD for the canonical financial_cells table (step 110).

    Key differences from the sandbox repository:
      - Stores numeric values, not formula text + spec_json.
      - Each cell can be linked to exactly one thesis_pillar (FK).
      - Each cell optionally records promoted_from_spec for lineage back
        to the sandbox spec that produced it (step 141 sets this).
      - artifact_status reflects the cell's lifecycle in the canonical
        model; the validator also reads this column.

    The schema enforces:
      - UNIQUE(project_id, scenario, cell_ref)
      - CHECK on artifact_status
      - FK from project_id, thesis_pillar_id (nullable), promoted_from_spec
    """

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def upsert_cell(
        self,
        *,
        project_id: UUID,
        scenario: str,
        cell_ref: str,
        label: str,
        value: Decimal | float | int,
        formula: str,
        thesis_pillar_id: UUID | None = None,
        promoted_from_spec: UUID | None = None,
        unit: str | None = None,
        source_refs: list[str] | None = None,
        ingestion_source_type: str = "manual_entry",
        parser_provenance: dict[str, Any] | None = None,
        phase_scope_version: int | None = None,
        artifact_status: str = "active",
    ) -> FinancialCellRow:
        """Insert or update a cell keyed by (project_id, scenario, cell_ref).

        Used by the promotion step (141) and by direct cell writes from
        the validator pipeline. The upsert keeps the unique constraint
        satisfied when the same logical cell is re-promoted.
        """
        _validate_status(artifact_status)
        value_dec = value if isinstance(value, Decimal) else Decimal(str(value))
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO financial_cells (
                        project_id, thesis_pillar_id, promoted_from_spec,
                        scenario, cell_ref, label, value, unit, formula,
                        source_refs, ingestion_source_type, parser_provenance,
                        phase_scope_version, artifact_status
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s::jsonb,
                        %s, %s
                    )
                    ON CONFLICT (project_id, scenario, cell_ref) DO UPDATE SET
                        thesis_pillar_id = EXCLUDED.thesis_pillar_id,
                        promoted_from_spec = EXCLUDED.promoted_from_spec,
                        label = EXCLUDED.label,
                        value = EXCLUDED.value,
                        unit = EXCLUDED.unit,
                        formula = EXCLUDED.formula,
                        source_refs = EXCLUDED.source_refs,
                        ingestion_source_type = EXCLUDED.ingestion_source_type,
                        parser_provenance = EXCLUDED.parser_provenance,
                        phase_scope_version = EXCLUDED.phase_scope_version,
                        artifact_status = EXCLUDED.artifact_status,
                        updated_at = now()
                    RETURNING *
                    """,
                    (
                        project_id,
                        thesis_pillar_id,
                        promoted_from_spec,
                        scenario,
                        cell_ref,
                        label,
                        value_dec,
                        unit,
                        formula,
                        list(source_refs or []),
                        ingestion_source_type,
                        json.dumps(parser_provenance or {}),
                        phase_scope_version,
                        artifact_status,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return self._to_row(row)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_cell(
        self, project_id: UUID, scenario: str, cell_ref: str
    ) -> FinancialCellRow | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM financial_cells
                    WHERE project_id = %s AND scenario = %s AND cell_ref = %s
                    """,
                    (project_id, scenario, cell_ref),
                )
                row = cur.fetchone()
                return self._to_row(row) if row else None

    def list_cells_by_project(
        self,
        project_id: UUID,
        scenario: str | None = None,
        artifact_status: str | None = None,
    ) -> list[FinancialCellRow]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if scenario and artifact_status:
                    cur.execute(
                        """
                        SELECT * FROM financial_cells
                        WHERE project_id = %s AND scenario = %s
                          AND artifact_status = %s
                        ORDER BY cell_ref ASC
                        """,
                        (project_id, scenario, artifact_status),
                    )
                elif scenario:
                    cur.execute(
                        """
                        SELECT * FROM financial_cells
                        WHERE project_id = %s AND scenario = %s
                        ORDER BY cell_ref ASC
                        """,
                        (project_id, scenario),
                    )
                elif artifact_status:
                    cur.execute(
                        """
                        SELECT * FROM financial_cells
                        WHERE project_id = %s AND artifact_status = %s
                        ORDER BY cell_ref ASC
                        """,
                        (project_id, artifact_status),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM financial_cells
                        WHERE project_id = %s
                        ORDER BY cell_ref ASC
                        """,
                        (project_id,),
                    )
                rows = cur.fetchall()
                return [self._to_row(r) for r in rows]

    def list_cells_for_pillar(
        self, thesis_pillar_id: UUID
    ) -> list[FinancialCellRow]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM financial_cells
                    WHERE thesis_pillar_id = %s
                    ORDER BY scenario, cell_ref
                    """,
                    (thesis_pillar_id,),
                )
                rows = cur.fetchall()
                return [self._to_row(r) for r in rows]

    def list_cells_from_spec(
        self, promoted_from_spec: UUID
    ) -> list[FinancialCellRow]:
        """Cells promoted from a given sandbox spec (lineage lookup)."""
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM financial_cells
                    WHERE promoted_from_spec = %s
                    ORDER BY scenario, cell_ref
                    """,
                    (promoted_from_spec,),
                )
                rows = cur.fetchall()
                return [self._to_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Mutate
    # ------------------------------------------------------------------

    def set_artifact_status(
        self,
        project_id: UUID,
        scenario: str,
        cell_ref: str,
        status: str,
    ) -> None:
        _validate_status(status)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE financial_cells
                    SET artifact_status = %s, updated_at = now()
                    WHERE project_id = %s AND scenario = %s AND cell_ref = %s
                    """,
                    (status, project_id, scenario, cell_ref),
                )
                conn.commit()

    def set_phase_scope_version(
        self,
        project_id: UUID,
        scenario: str,
        cell_ref: str,
        phase_scope_version: int,
    ) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE financial_cells
                    SET phase_scope_version = %s, updated_at = now()
                    WHERE project_id = %s AND scenario = %s AND cell_ref = %s
                    """,
                    (phase_scope_version, project_id, scenario, cell_ref),
                )
                conn.commit()

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _to_row(row: dict[str, Any]) -> FinancialCellRow:
        return FinancialCellRow(
            id=row["id"],
            project_id=row["project_id"],
            thesis_pillar_id=row["thesis_pillar_id"],
            promoted_from_spec=row["promoted_from_spec"],
            scenario=row["scenario"],
            cell_ref=row["cell_ref"],
            label=row["label"],
            value=row["value"],
            unit=row["unit"],
            formula=row["formula"],
            source_refs=list(row["source_refs"] or []),
            ingestion_source_type=row["ingestion_source_type"],
            parser_provenance=(
                json.loads(row["parser_provenance"])
                if row["parser_provenance"]
                else {}
            ),
            phase_scope_version=row["phase_scope_version"],
            artifact_status=row["artifact_status"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
