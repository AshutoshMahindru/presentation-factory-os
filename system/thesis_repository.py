from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from psycopg.rows import dict_row

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool


@dataclass(frozen=True)
class ThesisVersion:
    id: UUID
    project_id: UUID
    version_number: int
    thesis_statement: str
    convergence_score: float | None
    created_at: str


@dataclass(frozen=True)
class ThesisPillar:
    id: UUID
    thesis_version_id: UUID
    pillar_index: int
    pillar_type: str
    statement: str
    stress_status: str


@dataclass(frozen=True)
class ResearchLoop:
    id: UUID
    project_id: UUID
    loop_number: int
    convergence_delta: float | None
    sources_discovered_count: int
    status: str
    created_at: str
    completed_at: str | None


class ThesisRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create_thesis_version(self, project_id: UUID, version_number: int, thesis_statement: str) -> ThesisVersion:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "INSERT INTO thesis_versions (project_id, version_number, thesis_statement) VALUES (%s, %s, %s) RETURNING *",
                    (project_id, version_number, thesis_statement),
                )
                row = cur.fetchone()
                conn.commit()
                return self._to_version(row)

    def get_latest_thesis(self, project_id: UUID) -> ThesisVersion | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM thesis_versions WHERE project_id = %s ORDER BY version_number DESC LIMIT 1",
                    (project_id,),
                )
                row = cur.fetchone()
                return self._to_version(row) if row else None

    def update_convergence_score(self, thesis_version_id: UUID, score: float) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE thesis_versions SET convergence_score = %s WHERE id = %s",
                    (score, thesis_version_id),
                )
                conn.commit()

    def create_pillar(self, thesis_version_id: UUID, pillar_index: int, pillar_type: str, statement: str) -> ThesisPillar:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "INSERT INTO thesis_pillars (thesis_version_id, pillar_index, pillar_type, statement) VALUES (%s, %s, %s, %s) RETURNING *",
                    (thesis_version_id, pillar_index, pillar_type, statement),
                )
                row = cur.fetchone()
                conn.commit()
                return self._to_pillar(row)

    def get_pillars(self, thesis_version_id: UUID) -> list[ThesisPillar]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM thesis_pillars WHERE thesis_version_id = %s ORDER BY pillar_index ASC",
                    (thesis_version_id,),
                )
                rows = cur.fetchall()
                return [self._to_pillar(r) for r in rows]

    def mark_pillar_stressed(self, pillar_id: UUID) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE thesis_pillars SET stress_status = 'stressed' WHERE id = %s",
                    (pillar_id,),
                )
                conn.commit()

    def start_research_loop(self, project_id: UUID, loop_number: int) -> ResearchLoop:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "INSERT INTO research_loops (project_id, loop_number) VALUES (%s, %s) RETURNING *",
                    (project_id, loop_number),
                )
                row = cur.fetchone()
                conn.commit()
                return self._to_loop(row)

    def finalize_research_loop(
        self,
        loop_id: UUID,
        convergence_delta: float,
        sources_discovered_count: int,
        status: str,
    ) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE research_loops SET convergence_delta = %s, sources_discovered_count = %s, status = %s, completed_at = now() WHERE id = %s",
                    (convergence_delta, sources_discovered_count, status, loop_id),
                )
                conn.commit()

    def get_loop(self, loop_id: UUID) -> ResearchLoop | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM research_loops WHERE id = %s", (loop_id,))
                row = cur.fetchone()
                return self._to_loop(row) if row else None

    @staticmethod
    def _to_version(row: dict[str, Any]) -> ThesisVersion:
        return ThesisVersion(
            id=row["id"],
            project_id=row["project_id"],
            version_number=row["version_number"],
            thesis_statement=row["thesis_statement"],
            convergence_score=row["convergence_score"],
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _to_pillar(row: dict[str, Any]) -> ThesisPillar:
        return ThesisPillar(
            id=row["id"],
            thesis_version_id=row["thesis_version_id"],
            pillar_index=row["pillar_index"],
            pillar_type=row["pillar_type"],
            statement=row["statement"],
            stress_status=row["stress_status"],
        )

    @staticmethod
    def _to_loop(row: dict[str, Any]) -> ResearchLoop:
        return ResearchLoop(
            id=row["id"],
            project_id=row["project_id"],
            loop_number=row["loop_number"],
            convergence_delta=row["convergence_delta"],
            sources_discovered_count=row["sources_discovered_count"],
            status=row["status"],
            created_at=str(row["created_at"]),
            completed_at=str(row["completed_at"]) if row["completed_at"] else None,
        )
