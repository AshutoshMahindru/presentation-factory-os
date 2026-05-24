from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


COMPOSE_FILE = "docker-compose.apps.yaml"


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    name: str
    audience: str
    audience_profile: dict[str, Any]
    current_phase: str


class ProjectRepository:
    """
    Baby-step Postgres-backed project repository.

    Uses docker compose + psql for now so we do not introduce connection pooling
    before the schema/repository contract is proven.
    """

    def create_project(
        self,
        name: str,
        audience: str,
        audience_profile: dict[str, Any],
        client_name: str | None = None,
        decision_required: str | None = None,
        objection_preemption_map: dict[str, Any] | None = None,
    ) -> ProjectRecord:
        audience_profile_json = self._json(audience_profile)
        objection_map_json = self._json(objection_preemption_map or {})

        sql = f"""
        INSERT INTO projects (
          name,
          client_name,
          audience,
          audience_profile,
          decision_required,
          objection_preemption_map,
          current_phase
        )
        VALUES (
          '{self._sql(name)}',
          {self._nullable(client_name)},
          '{self._sql(audience)}',
          '{audience_profile_json}'::jsonb,
          {self._nullable(decision_required)},
          '{objection_map_json}'::jsonb,
          'created'
        )
        RETURNING id, name, audience, audience_profile::text, current_phase;
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        return self._parse_project_record(result.stdout)

    def get_project(self, project_id: str) -> ProjectRecord | None:
        sql = f"""
        SELECT id, name, audience, audience_profile::text, current_phase
        FROM projects
        WHERE id = '{self._sql(project_id)}';
        """
        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        if not result.stdout.strip():
            return None

        return self._parse_project_record(result.stdout)

    def update_phase(self, project_id: str, to_phase: str) -> None:
        sql = f"""
        UPDATE projects
        SET current_phase = '{self._sql(to_phase)}',
            updated_at = now()
        WHERE id = '{self._sql(project_id)}';
        """
        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

    def _parse_project_record(self, stdout: str) -> ProjectRecord:
        for line in stdout.splitlines():
            if "|" not in line:
                continue

            parts = [part.strip() for part in line.split("|", maxsplit=4)]
            if len(parts) != 5:
                continue

            project_id, name, audience, audience_profile_text, current_phase = parts

            if project_id == "id":
                continue

            return ProjectRecord(
                project_id=project_id,
                name=name,
                audience=audience,
                audience_profile=json.loads(audience_profile_text),
                current_phase=current_phase,
            )

        raise RuntimeError(f"Could not parse project record from psql output: {stdout}")

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

    def _json(self, value: dict[str, Any]) -> str:
        return self._sql(json.dumps(value, separators=(",", ":")))

    def _sql(self, value: str) -> str:
        return str(value).replace("'", "''")

    def _nullable(self, value: str | None) -> str:
        if value is None:
            return "NULL"
        return f"'{self._sql(value)}'"
