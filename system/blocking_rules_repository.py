from __future__ import annotations

from dataclasses import dataclass

from system.db import execute_psql


@dataclass(frozen=True)
class BlockingRulesStatus:
    project_id: str
    blocked: bool
    blocking_count: int
    warning_count: int
    info_count: int


class BlockingRulesRepository:
    """
    Deterministic Postgres-backed blocking-rule status reader.

    Baby Step 50 supports two schema shapes:
    1. A future/project table called blocking_rules with project_id, severity, resolved.
    2. If that table is not present yet, it safely returns a clean status.

    This lets the hard-gate bundle become deterministic now without breaking the
    current schema while preserving the runtime contract for later expansion.
    """

    def get_project_blocking_rules_status(self, project_id: str) -> BlockingRulesStatus:
        exists_sql = """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.tables
          WHERE table_schema = 'public'
            AND table_name = 'blocking_rules'
        );
        """

        exists_result = self._psql(exists_sql)
        if exists_result.returncode != 0:
            raise RuntimeError(exists_result.stderr)

        table_exists = exists_result.stdout.strip().lower() in {"t", "true"}

        if not table_exists:
            return BlockingRulesStatus(
                project_id=project_id,
                blocked=False,
                blocking_count=0,
                warning_count=0,
                info_count=0,
            )

        sql = f"""
        SELECT
          count(*) FILTER (WHERE severity = 'blocking' AND resolved = FALSE) AS blocking_count,
          count(*) FILTER (WHERE severity = 'warning' AND resolved = FALSE) AS warning_count,
          count(*) FILTER (WHERE severity = 'info' AND resolved = FALSE) AS info_count
        FROM blocking_rules
        WHERE project_id = '{self._sql(project_id)}';
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        line = result.stdout.strip()
        if not line:
            return BlockingRulesStatus(
                project_id=project_id,
                blocked=False,
                blocking_count=0,
                warning_count=0,
                info_count=0,
            )

        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3:
            raise RuntimeError(f"Unexpected blocking rules status result: {result.stdout!r}")

        blocking_count = self._parse_int(parts[0])
        warning_count = self._parse_int(parts[1])
        info_count = self._parse_int(parts[2])

        return BlockingRulesStatus(
            project_id=project_id,
            blocked=blocking_count > 0,
            blocking_count=blocking_count,
            warning_count=warning_count,
            info_count=info_count,
        )

    def _psql(self, sql: str):
        return execute_psql(sql)

    def _parse_int(self, value: str) -> int:
        if value == "":
            return 0
        return int(value)

    def _sql(self, value: str) -> str:
        return str(value).replace("'", "''")
