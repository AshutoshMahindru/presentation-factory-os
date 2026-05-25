from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any, Callable

from neo4j import GraphDatabase

from system.neo4j_retraction_handler import Neo4jSourceRetractionHandler
from system.outbox_repository import OutboxRepository, PendingOutboxRow


OutboxHandler = Callable[[PendingOutboxRow], None]
Neo4jDriverFactory = Callable[..., Any]


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


@dataclass(frozen=True)
class Neo4jConnectionConfig:
    uri: str
    user: str
    password: str
    database: str | None = None

    @classmethod
    def from_env(cls) -> "Neo4jConnectionConfig":
        user = os.environ.get("NEO4J_USER", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD")

        auth = os.environ.get("NEO4J_AUTH", "")
        if password is None and "/" in auth:
            auth_user, auth_password = auth.split("/", 1)
            user = os.environ.get("NEO4J_USER", auth_user)
            password = auth_password

        return cls(
            uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            user=user,
            password=password or "pfos_neo4j_password",
            database=os.environ.get("NEO4J_DATABASE") or None,
        )


class Neo4jProjectNodeHandler:
    """
    Backward-compatible Neo4j handler for current integration tests.

    Existing tests expect idempotent Project node MERGE using:
      (:Project {id: <project_id>})

    The handler supports legacy outbox payloads for claim_updated,
    phase_transition_side_effect, and retreat_archive_downstream rows.
    """

    def __init__(
        self,
        config: Neo4jConnectionConfig | None = None,
        driver_factory: Neo4jDriverFactory | None = None,
    ) -> None:
        self.config = config or Neo4jConnectionConfig.from_env()
        self.driver_factory = driver_factory or GraphDatabase.driver

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

        driver = self.driver_factory(
            self.config.uri,
            auth=(self.config.user, self.config.password),
        )
        try:
            session_options = {}
            if self.config.database:
                session_options["database"] = self.config.database

            with driver.session(**session_options) as session:
                session.execute_write(
                    self._merge_project_node,
                    project_id=project_id,
                    name=name or None,
                    current_phase=current_phase or None,
                )
        finally:
            driver.close()

    @staticmethod
    def _merge_project_node(
        tx: Any,
        *,
        project_id: str,
        name: str | None,
        current_phase: str | None,
    ) -> None:
        result = tx.run(
            """
            MERGE (p:Project {id: $project_id})
            SET
              p.updated_at = datetime(),
              p.name = coalesce($name, p.name),
              p.current_phase = coalesce($current_phase, p.current_phase)
            RETURN p.id AS id
            """,
            project_id=project_id,
            name=name,
            current_phase=current_phase,
        )
        result.consume()


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

    def run_once(
        self,
        target_store: str = "neo4j",
        limit: int = 50,
        project_id: str | None = None,
        dry_run: bool = False,
    ) -> OutboxWorkerResult:
        rows = self.outbox_repository.list_unprocessed_rows(
            target_store=target_store,
            limit=limit,
            project_id=project_id,
        )

        scanned_count = len(rows)
        if dry_run:
            return OutboxWorkerResult(
                scanned_count=scanned_count,
                processed_count=0,
                failed_count=0,
            )

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one outbox worker pass.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan unprocessed outbox rows without invoking handlers or mutating rows.",
    )
    args = parser.parse_args(argv)

    result = OutboxWorker().run_once(dry_run=args.dry_run)
    print(result.as_cli_line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
