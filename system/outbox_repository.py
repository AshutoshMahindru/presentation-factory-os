from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


COMPOSE_FILE = "docker-compose.apps.yaml"


@dataclass(frozen=True)
class OutboxStatus:
    project_id: str
    blocked: bool
    unprocessed_count: int
    failed_count: int
    oldest_unprocessed_age_seconds: int | None


@dataclass(frozen=True)
class OutboxRow:
    outbox_id: str
    project_id: str
    target_store: str
    operation_type: str
    processed: bool


class OutboxRepository:
    """
    Deterministic Postgres-backed outbox repository.

    A project is blocked when it has any unprocessed outbox rows or any
    unprocessed rows with error_count > 0. This repository centralizes the
    outbox blocking query so workflow transitions, health endpoints, and
    export gates do not drift.
    """

    ALLOWED_TARGET_STORES = {"neo4j"}
    ALLOWED_OPERATION_TYPES = {
        "source_retracted",
        "claim_updated",
        "phase_transition_side_effect",
        "retreat_archive_downstream",
    }

    def create_outbox_row(
        self,
        project_id: str,
        target_store: str,
        operation_type: str,
        payload: dict[str, Any],
    ) -> OutboxRow:
        if target_store not in self.ALLOWED_TARGET_STORES:
            raise ValueError(f"Unsupported target_store: {target_store}")

        if operation_type not in self.ALLOWED_OPERATION_TYPES:
            raise ValueError(f"Unsupported operation_type: {operation_type}")

        payload_json = self._json(payload)

        sql = f"""
        INSERT INTO outbox (
          project_id,
          target_store,
          operation_type,
          payload,
          processed
        )
        VALUES (
          '{self._sql(project_id)}',
          '{self._sql(target_store)}',
          '{self._sql(operation_type)}',
          '{payload_json}'::jsonb,
          FALSE
        )
        RETURNING id, project_id, target_store, operation_type, processed;
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        line = result.stdout.strip()
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 5:
            raise RuntimeError(f"Unexpected outbox insert result: {result.stdout!r}")

        return OutboxRow(
            outbox_id=parts[0],
            project_id=parts[1],
            target_store=parts[2],
            operation_type=parts[3],
            processed=parts[4].lower() in {"t", "true"},
        )

    def get_project_outbox_status(self, project_id: str) -> OutboxStatus:
        sql = f"""
        SELECT
          count(*) FILTER (WHERE processed = FALSE) AS unprocessed_count,
          count(*) FILTER (WHERE processed = FALSE AND error_count > 0) AS failed_count,
          floor(
            extract(
              epoch FROM (
                now() - min(created_at) FILTER (WHERE processed = FALSE)
              )
            )
          )::int AS oldest_unprocessed_age_seconds
        FROM outbox
        WHERE project_id = '{self._sql(project_id)}';
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        line = result.stdout.strip()
        if not line:
            return OutboxStatus(
                project_id=project_id,
                blocked=False,
                unprocessed_count=0,
                failed_count=0,
                oldest_unprocessed_age_seconds=None,
            )

        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3:
            raise RuntimeError(f"Unexpected outbox status result: {result.stdout!r}")

        unprocessed_count = self._parse_int(parts[0])
        failed_count = self._parse_int(parts[1])
        oldest_age = self._parse_optional_int(parts[2])

        return OutboxStatus(
            project_id=project_id,
            blocked=unprocessed_count > 0 or failed_count > 0,
            unprocessed_count=unprocessed_count,
            failed_count=failed_count,
            oldest_unprocessed_age_seconds=oldest_age,
        )

    def project_has_blocking_outbox_rows(self, project_id: str) -> tuple[bool, int]:
        status = self.get_project_outbox_status(project_id)
        return status.blocked, status.unprocessed_count + status.failed_count

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
