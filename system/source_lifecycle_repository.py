from __future__ import annotations

from dataclasses import dataclass

from system.db import execute_psql


@dataclass(frozen=True)
class RetractionCascadeStatus:
    project_id: str
    blocked: bool
    pending_count: int
    processing_count: int
    failed_count: int
    oldest_open_age_seconds: int | None


@dataclass(frozen=True)
class SourceRetractionInvalidationResult:
    project_id: str
    source_id: str
    stale_financial_cells_count: int


class SourceLifecycleRepository:
    """
    Deterministic Postgres-backed source lifecycle status reader.

    A project is blocked when it has any open retraction cascade event in
    pending, processing, or failed state.
    """

    OPEN_STATUSES = ("pending", "processing", "failed")

    def get_project_retraction_cascade_status(self, project_id: str) -> RetractionCascadeStatus:
        sql = f"""
        SELECT
          count(*) FILTER (WHERE processing_status = 'pending') AS pending_count,
          count(*) FILTER (WHERE processing_status = 'processing') AS processing_count,
          count(*) FILTER (WHERE processing_status = 'failed') AS failed_count,
          floor(
            extract(
              epoch FROM (
                now() - min(created_at) FILTER (
                  WHERE processing_status IN ('pending', 'processing', 'failed')
                )
              )
            )
          )::int AS oldest_open_age_seconds
        FROM source_lifecycle_events
        WHERE project_id = '{self._sql(project_id)}'
          AND event_type = 'retracted'
          AND processing_status IN ('pending', 'processing', 'failed');
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        line = result.stdout.strip()
        if not line:
            return RetractionCascadeStatus(
                project_id=project_id,
                blocked=False,
                pending_count=0,
                processing_count=0,
                failed_count=0,
                oldest_open_age_seconds=None,
            )

        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 4:
            raise RuntimeError(f"Unexpected retraction cascade status result: {result.stdout!r}")

        pending_count = self._parse_int(parts[0])
        processing_count = self._parse_int(parts[1])
        failed_count = self._parse_int(parts[2])
        oldest_age = self._parse_optional_int(parts[3])

        return RetractionCascadeStatus(
            project_id=project_id,
            blocked=(pending_count + processing_count + failed_count) > 0,
            pending_count=pending_count,
            processing_count=processing_count,
            failed_count=failed_count,
            oldest_open_age_seconds=oldest_age,
        )

    def invalidate_financial_cells_for_retracted_source(
        self,
        project_id: str,
        source_id: str,
    ) -> SourceRetractionInvalidationResult:
        if not project_id or not project_id.strip():
            raise ValueError("project_id is required")
        if not source_id or not source_id.strip():
            raise ValueError("source_id is required")

        sql = f"""
        WITH stale_financial_cells AS (
          UPDATE financial_cells
          SET artifact_status = 'stale_due_to_retreat',
              updated_at = now()
          WHERE project_id = '{self._sql(project_id)}'
            AND artifact_status = 'active'
            AND '{self._sql(source_id)}' = ANY(source_refs)
          RETURNING id
        )
        SELECT count(*)::int
        FROM stale_financial_cells;
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        return SourceRetractionInvalidationResult(
            project_id=project_id,
            source_id=source_id,
            stale_financial_cells_count=self._parse_int(result.stdout.strip()),
        )

    def _psql(self, sql: str):
        return execute_psql(sql)

    def _parse_int(self, value: str) -> int:
        if value == "":
            return 0
        return int(value)

    def _parse_optional_int(self, value: str) -> int | None:
        if value == "":
            return None
        return int(value)

    def _sql(self, value: str) -> str:
        return str(value).replace("'", "''")
