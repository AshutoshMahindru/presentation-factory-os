from __future__ import annotations

import subprocess
from dataclasses import dataclass


COMPOSE_FILE = "docker-compose.apps.yaml"


@dataclass(frozen=True)
class StaleArtifactStatus:
    project_id: str
    blocked: bool
    financial_cells_count: int
    design_tokens_count: int
    total_count: int


class StaleArtifactRepository:
    """
    Deterministic Postgres-backed stale artifact status reader.

    A project is blocked when any scoped artifact is marked stale_due_to_retreat.
    Baby Step 48 covers the current Postgres artifact tables that already expose
    artifact_status: financial_cells and design_tokens.
    """

    def get_project_stale_artifact_status(self, project_id: str) -> StaleArtifactStatus:
        sql = f"""
        SELECT
          (
            SELECT count(*)
            FROM financial_cells
            WHERE project_id = '{self._sql(project_id)}'
              AND artifact_status = 'stale_due_to_retreat'
          ) AS financial_cells_count,
          (
            SELECT count(*)
            FROM design_tokens
            WHERE project_id = '{self._sql(project_id)}'
              AND artifact_status = 'stale_due_to_retreat'
          ) AS design_tokens_count;
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        line = result.stdout.strip()
        if not line:
            return StaleArtifactStatus(
                project_id=project_id,
                blocked=False,
                financial_cells_count=0,
                design_tokens_count=0,
                total_count=0,
            )

        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 2:
            raise RuntimeError(f"Unexpected stale artifact status result: {result.stdout!r}")

        financial_cells_count = self._parse_int(parts[0])
        design_tokens_count = self._parse_int(parts[1])
        total_count = financial_cells_count + design_tokens_count

        return StaleArtifactStatus(
            project_id=project_id,
            blocked=total_count > 0,
            financial_cells_count=financial_cells_count,
            design_tokens_count=design_tokens_count,
            total_count=total_count,
        )

    def _psql(self, sql: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                COMPOSE_FILE,
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "pfos",
                "-d",
                "pfos",
                "-v",
                "ON_ERROR_STOP=1",
                "-A",
                "-t",
                "-F",
                "|",
                "-c",
                sql,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _parse_int(self, value: str) -> int:
        if value == "":
            return 0
        return int(value)

    def _sql(self, value: str) -> str:
        return str(value).replace("'", "''")
