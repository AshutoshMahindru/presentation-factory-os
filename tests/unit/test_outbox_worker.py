from __future__ import annotations

from jobs.outbox_worker import OutboxWorker
from system.outbox_repository import PendingOutboxRow


class FakeOutboxRepository:
    def __init__(self, rows: list[PendingOutboxRow]) -> None:
        self.rows = rows
        self.list_calls: list[dict[str, object]] = []
        self.processed: list[str] = []
        self.failed: list[dict[str, str]] = []

    def list_unprocessed_rows(self, target_store: str = "neo4j", limit: int = 50) -> list[PendingOutboxRow]:
        self.list_calls.append({"target_store": target_store, "limit": limit})
        return self.rows

    def mark_processed(self, outbox_id: str) -> None:
        self.processed.append(outbox_id)

    def mark_failed(self, outbox_id: str, last_error: str) -> None:
        self.failed.append({"outbox_id": outbox_id, "last_error": last_error})


def make_row(operation_type: str = "source_retracted") -> PendingOutboxRow:
    return PendingOutboxRow(
        outbox_id="outbox-1",
        project_id="project-1",
        target_store="neo4j",
        operation_type=operation_type,
        payload={"source_id": "source-1"},
        error_count=0,
    )


def test_outbox_worker_no_rows() -> None:
    repository = FakeOutboxRepository([])
    worker = OutboxWorker(outbox_repository=repository, handlers={})

    result = worker.run_once(limit=10)

    assert result.scanned_count == 0
    assert result.processed_count == 0
    assert result.failed_count == 0
    assert repository.list_calls == [{"target_store": "neo4j", "limit": 10}]
    assert repository.processed == []
    assert repository.failed == []


def test_outbox_worker_dispatches_handler_and_marks_processed() -> None:
    row = make_row()
    repository = FakeOutboxRepository([row])
    handled: list[PendingOutboxRow] = []

    worker = OutboxWorker(
        outbox_repository=repository,
        handlers={"source_retracted": lambda pending_row: handled.append(pending_row)},
    )

    result = worker.run_once()

    assert result.scanned_count == 1
    assert result.processed_count == 1
    assert result.failed_count == 0
    assert handled == [row]
    assert repository.processed == ["outbox-1"]
    assert repository.failed == []


def test_outbox_worker_marks_failed_when_handler_missing() -> None:
    row = make_row(operation_type="unknown_operation")
    repository = FakeOutboxRepository([row])
    worker = OutboxWorker(outbox_repository=repository, handlers={})

    result = worker.run_once()

    assert result.scanned_count == 1
    assert result.processed_count == 0
    assert result.failed_count == 1
    assert repository.processed == []
    assert repository.failed == [
        {
            "outbox_id": "outbox-1",
            "last_error": "No outbox handler registered for operation_type: unknown_operation",
        }
    ]


def test_outbox_worker_marks_failed_when_handler_raises() -> None:
    row = make_row()
    repository = FakeOutboxRepository([row])

    def failing_handler(pending_row: PendingOutboxRow) -> None:
        raise RuntimeError("neo4j unavailable")

    worker = OutboxWorker(
        outbox_repository=repository,
        handlers={"source_retracted": failing_handler},
    )

    result = worker.run_once()

    assert result.scanned_count == 1
    assert result.processed_count == 0
    assert result.failed_count == 1
    assert repository.processed == []
    assert repository.failed == [
        {
            "outbox_id": "outbox-1",
            "last_error": "neo4j unavailable",
        }
    ]
