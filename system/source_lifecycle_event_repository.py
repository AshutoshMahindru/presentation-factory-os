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
    Deterministic Postgres-backed source lifecycle event repository.

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

    ALLOWED_PROCESSING_STATUSES = {
        "pending",
        "processing",
        "processed",
        "failed",
        "blocked",
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

        if processing_status not in self.ALLOWED_PROCESSING_STATUSES:
            raise ValueError(f"Unsupported processing_status: {processing_status}")

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

        return self._parse_event_result(result.stdout)

    def list_pending_retraction_events(self, limit: int = 50) -> list[SourceLifecycleEvent]:
        if limit <= 0 or limit > 50:
            raise ValueError("limit must be between 1 and 50")

        sql = f"""
        SELECT id, project_id, source_id, event_type, processing_status
        FROM source_lifecycle_events
        WHERE event_type = 'retracted'
          AND processing_status = 'pending'
        ORDER BY created_at ASC
        LIMIT {int(limit)};
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        events: list[SourceLifecycleEvent] = []
        for line in result.stdout.splitlines():
            if "|" not in line:
                continue
            events.append(self._parse_event_result(line))

        return events

    def update_processing_status(
        self,
        event_id: str,
        processing_status: str,
        last_error: str | None = None,
    ) -> SourceLifecycleEvent:
        if processing_status not in self.ALLOWED_PROCESSING_STATUSES:
            raise ValueError(f"Unsupported processing_status: {processing_status}")

        processed_at_sql = "now()" if processing_status == "processed" else "processed_at"
        error_count_sql = "error_count + 1" if processing_status == "failed" else "error_count"

        sql = f"""
        UPDATE source_lifecycle_events
        SET
          processing_status = '{self._sql(processing_status)}',
          last_error = {self._nullable(last_error)},
          error_count = {error_count_sql},
          processed_at = {processed_at_sql}
        WHERE id = '{self._sql(event_id)}'
        RETURNING id, project_id, source_id, event_type, processing_status;
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        if not result.stdout.strip():
            raise LookupError(f"Source lifecycle event not found: {event_id}")

        return self._parse_event_result(result.stdout)

    def _parse_event_result(self, stdout: str) -> SourceLifecycleEvent:
        line = stdout.strip()
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 5:
            raise RuntimeError(f"Unexpected source lifecycle event result: {stdout!r}")

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
