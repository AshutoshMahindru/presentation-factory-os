from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from system.outbox_repository import OutboxRepository, PendingOutboxRow


OutboxHandler = Callable[[PendingOutboxRow], None]


@dataclass(frozen=True)
class OutboxWorkerResult:
    scanned_count: int
    processed_count: int
    failed_count: int


class OutboxWorker:
    """
    Deterministic outbox worker skeleton.

    The worker dispatches unprocessed rows to operation handlers. The first
    production handler can later write to Neo4j; this skeleton provides the
    retry/status mechanics around that handler.
    """

    def __init__(
        self,
        outbox_repository: OutboxRepository | None = None,
        handlers: dict[str, OutboxHandler] | None = None,
    ) -> None:
        self.outbox_repository = outbox_repository or OutboxRepository()
        self.handlers = handlers or {}

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
                self.outbox_repository.mark_failed(row.outbox_id, str(exc))

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
