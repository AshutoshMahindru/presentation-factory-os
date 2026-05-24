from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Callable

from system.neo4j_retraction_handler import Neo4jSourceRetractionHandler
from system.outbox_repository import OutboxRepository, PendingOutboxRow


OutboxHandler = Callable[[PendingOutboxRow], None]


@dataclass(frozen=True)
class OutboxWorkerResult:
    scanned_count: int
    processed_count: int
    failed_count: int

    def as_cli_line(self) -> str:
        return (
            f"processed_outbox_rows={self.processed_count} "
            f"failed_outbox_rows={self.failed_count} "
            f"scanned_outbox_rows={self.scanned_count}"
        )


class Neo4jProjectNodeHandler:
    """
    Backward-compatible Neo4j handler for current integration tests.

    Existing tests expect idempotent Project node MERGE using:
      (:Project {id: <project_id>})

    The handler supports legacy outbox payloads for claim_updated,
    phase_transition_side_effect, and retreat_archive_downstream rows.
    """

    def __call__(self, row: PendingOutboxRow) -> None:
        if os.environ.get("PFOS_FORCE_OUTBOX_FAILURE") == "1" or row.payload.get("force_error") is True:
            raise RuntimeError("Forced outbox operation failure")

        project_id = str(
            row.payload.get("project_id")
            or row.payload.get("id")
            or row.project_id
        )

        if not project_id:
            raise ValueError("Outbox payload requires project_id")

        name = str(row.payload.get("name") or row.payload.get("project_name") or "")
        current_phase = str(
            row.payload.get("current_phase")
            or row.payload.get("to_phase")
            or row.payload.get("phase")
            or ""
        )

        set_lines = ["p.updated_at = datetime()"]
        if name:
            set_lines.append(f"p.name = '{self._cypher(name)}'")
        if current_phase:
            set_lines.append(f"p.current_phase = '{self._cypher(current_phase)}'")

        cypher = f"""
        MERGE (p:Project {{id: '{self._cypher(project_id)}'}})
        SET {", ".join(set_lines)}
        RETURN p.id;
        """

        password = self._neo4j_password()

        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                "docker-compose.apps.yaml",
                "exec",
                "-T",
                "neo4j",
                "cypher-shell",
                "-u",
                "neo4j",
                "-p",
                password,
                cypher,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    def _neo4j_password(self) -> str:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                "docker-compose.apps.yaml",
                "exec",
                "-T",
                "neo4j",
                "printenv",
                "NEO4J_AUTH",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        auth = result.stdout.strip()
        if "/" in auth:
            return auth.split("/", 1)[1]

        return "pfos_neo4j_password"

    def _cypher(self, value: str) -> str:
        return str(value).replace("\\", "\\\\").replace("'", "\\'")


class OutboxWorker:
    """
    Deterministic outbox worker.

    It dispatches unprocessed outbox rows to operation handlers, marks rows
    processed on success, and records failure metadata on failure.
    """

    def __init__(
        self,
        outbox_repository: OutboxRepository | None = None,
        handlers: dict[str, OutboxHandler] | None = None,
    ) -> None:
        self.outbox_repository = outbox_repository or OutboxRepository()
        self.handlers = handlers if handlers is not None else self.default_handlers()

    @staticmethod
    def default_handlers() -> dict[str, OutboxHandler]:
        project_handler = Neo4jProjectNodeHandler()
        return {
            "claim_updated": project_handler,
            "phase_transition_side_effect": project_handler,
            "retreat_archive_downstream": project_handler,
            "source_retracted": Neo4jSourceRetractionHandler(),
        }

    def run_once(self, target_store: str = "neo4j", limit: int = 50) -> OutboxWorkerResult:
        rows = self.outbox_repository.list_unprocessed_rows(target_store=target_store, limit=limit)

        scanned_count = len(rows)
        processed_count = 0
        failed_count = 0

        for row in rows:
            try:
                self._process_row(row)
                processed_count += 1
            except Exception as exc:
                failed_count += 1
                try:
                    self.outbox_repository.mark_failed(row.outbox_id, str(exc))
                except Exception as mark_failed_exc:
                    print(
                        f"outbox_mark_failed_error outbox_id={row.outbox_id} error={mark_failed_exc}",
                    )

        return OutboxWorkerResult(
            scanned_count=scanned_count,
            processed_count=processed_count,
            failed_count=failed_count,
        )

    def _process_row(self, row: PendingOutboxRow) -> None:
        handler = self.handlers.get(row.operation_type)
        if handler is None:
            raise RuntimeError(f"No outbox handler registered for operation_type: {row.operation_type}")

        handler(row)
        self.outbox_repository.mark_processed(row.outbox_id)


def main() -> int:
    result = OutboxWorker().run_once()
    print(result.as_cli_line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
