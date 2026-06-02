from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from psycopg.rows import dict_row

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool


@dataclass(frozen=True)
class SourceRegisterRow:
    id: UUID
    project_id: UUID
    uri: str
    title: str | None
    source_type: str
    content_hash: str
    quality_score: dict[str, Any]
    search_coverage: list[dict[str, Any]]
    status: str
    created_at: str
    updated_at: str


class SourceRegisterRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @staticmethod
    def compute_content_hash(normalized_text: str) -> str:
        return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

    def create(
        self,
        project_id: UUID,
        uri: str,
        title: str | None,
        source_type: str,
        normalized_text: str,
        quality_score: dict[str, Any] | None = None,
    ) -> SourceRegisterRow:
        content_hash = self.compute_content_hash(normalized_text)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO source_register (project_id, uri, title, source_type, content_hash, quality_score)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (project_id, content_hash) DO UPDATE SET
                        status = 'active',
                        updated_at = now()
                    RETURNING *
                    """,
                    (project_id, uri, title, source_type, content_hash, json.dumps(quality_score or {})),
                )
                row = cur.fetchone()
                conn.commit()
                return self._to_row(row)

    def get(self, source_id: UUID) -> SourceRegisterRow | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM source_register WHERE id = %s", (source_id,))
                row = cur.fetchone()
                return self._to_row(row) if row else None

    def list_by_project(self, project_id: UUID, status: str | None = None) -> list[SourceRegisterRow]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if status:
                    cur.execute(
                        "SELECT * FROM source_register WHERE project_id = %s AND status = %s ORDER BY created_at DESC",
                        (project_id, status),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM source_register WHERE project_id = %s ORDER BY created_at DESC",
                        (project_id,),
                    )
                rows = cur.fetchall()
                return [self._to_row(r) for r in rows]

    def update_search_coverage(self, source_id: UUID, thesis_version_id: UUID, pillar_ids: list[UUID]) -> None:
        coverage_entry = {
            "thesis_version_id": str(thesis_version_id),
            "pillar_ids": [str(p) for p in pillar_ids],
        }
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE source_register
                    SET search_coverage = search_coverage || %s::jsonb,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (json.dumps([coverage_entry]), source_id),
                )
                conn.commit()

    def mark_retracted(self, source_id: UUID) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE source_register SET status = 'retracted', updated_at = now() WHERE id = %s",
                    (source_id,),
                )
                conn.commit()

    @staticmethod
    def _to_row(row: dict[str, Any]) -> SourceRegisterRow:
        return SourceRegisterRow(
            id=row["id"],
            project_id=row["project_id"],
            uri=row["uri"],
            title=row["title"],
            source_type=row["source_type"],
            content_hash=row["content_hash"],
            quality_score=json.loads(row["quality_score"]) if row["quality_score"] else {},
            search_coverage=json.loads(row["search_coverage"]) if row["search_coverage"] else [],
            status=row["status"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
