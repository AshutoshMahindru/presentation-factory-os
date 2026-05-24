from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any


DEFAULT_COMPOSE_FILE = "docker-compose.apps.yaml"


@dataclass(frozen=True)
class OutboxRow:
    id: str
    project_id: str
    operation_type: str
    payload: dict[str, Any]
    error_count: int


class OutboxWorker:
    """
    Minimal v1 outbox worker.

    This baby-step implementation uses docker-compose exec + psql so it can run
    without introducing a persistent Python DB connection layer yet.
    """

    def __init__(self, compose_file: str = DEFAULT_COMPOSE_FILE) -> None:
        self.compose_file = compose_file

    def process_once(self) -> int:
        rows = self.fetch_unprocessed(limit=10)
        processed_count = 0

        for row in rows:
            try:
                self.apply_operation(row)
                self.mark_processed(row.id)
                processed_count += 1
            except Exception as exc:  # deliberately broad for v1 worker safety
                self.mark_failed(row.id, str(exc))

        return processed_count

    def fetch_unprocessed(self, limit: int = 10) -> list[OutboxRow]:
        sql = f"""
        SELECT id, project_id, operation_type, payload::text, error_count
        FROM outbox
        WHERE processed = FALSE AND error_count < 5
        ORDER BY created_at ASC
        LIMIT {int(limit)};
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        rows: list[OutboxRow] = []
        for line in result.stdout.splitlines():
            if "|" not in line:
                continue

            parts = [part.strip() for part in line.split("|")]
            if len(parts) != 5:
                continue

            row_id, project_id, operation_type, payload_text, error_count = parts
            if row_id == "id" or row_id.startswith("-"):
                continue

            rows.append(
                OutboxRow(
                    id=row_id,
                    project_id=project_id,
                    operation_type=operation_type,
                    payload=json.loads(payload_text),
                    error_count=int(error_count),
                )
            )

        return rows

    def apply_operation(self, row: OutboxRow) -> None:
        """
        Applies one idempotent cross-store side effect.

        Baby Step 27 implements the first real Neo4j write:
        phase_transition_side_effect creates/updates a Project node.
        """
        allowed = {
            "source_retracted",
            "claim_updated",
            "phase_transition_side_effect",
            "retreat_archive_downstream",
        }

        if row.operation_type not in allowed:
            raise ValueError(f"Unsupported outbox operation_type: {row.operation_type}")

        if row.payload.get("force_error") is True:
            raise RuntimeError("Forced outbox operation failure for retry/backoff test.")

        if row.operation_type == "phase_transition_side_effect":
            self.apply_phase_transition_side_effect(row)

    def apply_phase_transition_side_effect(self, row: OutboxRow) -> None:
        project_name = str(row.payload.get("project_name", "Outbox Project")).replace("'", "''")
        current_phase = str(row.payload.get("to_phase", "unknown")).replace("'", "''")

        query = f"""
        MERGE (p:Project {{id: '{row.project_id}'}})
        SET p.name = '{project_name}',
            p.status = 'active',
            p.current_phase = '{current_phase}',
            p.updated_at = datetime()
        RETURN p.id AS project_id;
        """

        result = self._cypher(query)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

    def mark_processed(self, row_id: str) -> None:
        sql = f"""
        UPDATE outbox
        SET processed = TRUE,
            processed_at = now(),
            last_error = NULL
        WHERE id = '{row_id}';
        """
        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

    def mark_failed(self, row_id: str, error: str) -> None:
        safe_error = error.replace("'", "''")[:1000]
        sql = f"""
        UPDATE outbox
        SET error_count = error_count + 1,
            last_error = '{safe_error}'
        WHERE id = '{row_id}';
        """
        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

    def _psql(self, sql: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                self.compose_file,
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

    def _cypher(self, query: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                self.compose_file,
                "exec",
                "-T",
                "neo4j",
                "cypher-shell",
                "-u",
                "neo4j",
                "-p",
                "pfos_neo4j_password",
                query,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


def main() -> None:
    compose_file = os.environ.get("PFOS_COMPOSE_FILE", DEFAULT_COMPOSE_FILE)
    processed = OutboxWorker(compose_file=compose_file).process_once()
    print(f"processed_outbox_rows={processed}")


if __name__ == "__main__":
    main()
