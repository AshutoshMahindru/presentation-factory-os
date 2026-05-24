from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


COMPOSE_FILE = "docker-compose.apps.yaml"


@dataclass(frozen=True)
class SourceLifecycleEvent:
    event_id: str
    project_id: str
    source_id: str
    event_type: str
    processing_status: str


class SourceLifecycleEventRepository:
    """
    Deterministic Postgres-backed source lifecycle event writer.

    This repository writes authoritative lifecycle events into source_lifecycle_events.
    Retraction events are intentionally created as pending, so the hard-gate bundle
    can block transitions until the cascade processor marks them processed.
    """

    ALLOWED_EVENT_TYPES = {
        "created",
        "updated",
        "retracted",
        "classification_changed",
        "superseded",
    }

    def create_event(
        self,
        project_id: str,
        source_id: str,
        event_type: str,
        event_payload: dict[str, Any] | None = None,
        source_version: str | None = None,
        classification: str | None = None,
        hmac_validated: bool = False,
        processing_status: str = "pending",
    ) -> SourceLifecycleEvent:
        if event_type not in self.ALLOWED_EVENT_TYPES:
            raise ValueError(f"Unsupported lifecycle event_type: {event_type}")

        payload_json = self._json(event_payload or {})

        sql = f"""
        INSERT INTO source_lifecycle_events (
          project_id,
          source_id,
          event_type,
          source_version,
          classification,
          event_payload,
          hmac_validated,
          processing_status
        )
        VALUES (
          '{self._sql(project_id)}',
          '{self._sql(source_id)}',
          '{self._sql(event_type)}',
          {self._nullable(source_version)},
          {self._nullable(classification)},
          '{payload_json}'::jsonb,
          {str(hmac_validated).lower()},
          '{self._sql(processing_status)}'
        )
        RETURNING id, project_id, source_id, event_type, processing_status;
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        line = result.stdout.strip()
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 5:
            raise RuntimeError(f"Unexpected source lifecycle event insert result: {result.stdout!r}")

        return SourceLifecycleEvent(
            event_id=parts[0],
            project_id=parts[1],
            source_id=parts[2],
            event_type=parts[3],
            processing_status=parts[4],
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

    def _json(self, value: dict[str, Any]) -> str:
        return self._sql(json.dumps(value, sort_keys=True))

    def _nullable(self, value: str | None) -> str:
        if value is None:
            return "NULL"
        return f"'{self._sql(value)}'"

    def _sql(self, value: str) -> str:
        return str(value).replace("'", "''")
