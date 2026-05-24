from __future__ import annotations

import jobs.outbox_worker as outbox_worker
from jobs.outbox_worker import OutboxWorker, OutboxWorkerResult
from system.outbox_repository import PendingOutboxRow


class FakeOutboxRepository:
    def __init__(self, rows: list[PendingOutboxRow]) -> None:
        self.rows = rows
        self.list_calls: list[dict[str, object]] = []
        self.processed: list[str] = []
        self.failed: list[dict[str, str]] = []

    def list_unprocessed_rows(
        self,
        target_store: str = "neo4j",
        limit: int = 50,
        project_id: str | None = None,
    ) -> list[PendingOutboxRow]:
        self.list_calls.append({"target_store": target_store, "limit": limit, "project_id": project_id})
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
    assert repository.list_calls == [{"target_store": "neo4j", "limit": 10, "project_id": None}]
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


def test_outbox_worker_dry_run_scans_without_handlers_or_mutation() -> None:
    row = make_row()
    repository = FakeOutboxRepository([row])
    handled: list[PendingOutboxRow] = []

    worker = OutboxWorker(
        outbox_repository=repository,
        handlers={"source_retracted": lambda pending_row: handled.append(pending_row)},
    )

    result = worker.run_once(limit=10, dry_run=True)

    assert result.scanned_count == 1
    assert result.processed_count == 0
    assert result.failed_count == 0
    assert repository.list_calls == [{"target_store": "neo4j", "limit": 10, "project_id": None}]
    assert handled == []
    assert repository.processed == []
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


def test_neo4j_project_handler_uses_id_property_and_payload_fields(monkeypatch) -> None:
    import jobs.outbox_worker as outbox_worker
    from jobs.outbox_worker import Neo4jProjectNodeHandler

    commands: list[list[str]] = []

    class FakeResult:
        returncode = 0
        stdout = "neo4j/pfos_neo4j_password\n"
        stderr = ""

    def fake_run(command, text, stdout, stderr, check):
        commands.append(command)
        if "printenv" in command:
            return FakeResult()

        class CypherResult:
            returncode = 0
            stdout = "id\nproject-1\n"
            stderr = ""

        return CypherResult()

    monkeypatch.setattr(outbox_worker.subprocess, "run", fake_run)

    row = PendingOutboxRow(
        outbox_id="outbox-1",
        project_id="project-1",
        target_store="neo4j",
        operation_type="phase_transition_side_effect",
        payload={
            "project_id": "project-1",
            "name": "Demo Project",
            "current_phase": "strategy",
        },
        error_count=0,
    )

    Neo4jProjectNodeHandler()(row)

    cypher_command = commands[-1]
    cypher = cypher_command[-1]

    assert "MERGE (p:Project {id: 'project-1'})" in cypher
    assert "p.name = 'Demo Project'" in cypher
    assert "p.current_phase = 'strategy'" in cypher
    assert "project_id:" not in cypher


def test_outbox_worker_default_source_retracted_handler_is_contract_validator() -> None:
    row = PendingOutboxRow(
        outbox_id="outbox-source-retracted-1",
        project_id="project-1",
        target_store="neo4j",
        operation_type="source_retracted",
        payload={
            "source_lifecycle_event_id": "event-1",
            "project_id": "project-1",
            "source_id": "source-1",
            "event_type": "retracted",
        },
        error_count=0,
    )
    repository = FakeOutboxRepository([row])
    worker = OutboxWorker(outbox_repository=repository)

    result = worker.run_once()

    assert result.scanned_count == 1
    assert result.processed_count == 1
    assert result.failed_count == 0
    assert repository.processed == ["outbox-source-retracted-1"]
    assert repository.failed == []


def test_outbox_worker_default_source_retracted_handler_fails_invalid_payload() -> None:
    row = PendingOutboxRow(
        outbox_id="outbox-source-retracted-2",
        project_id="project-1",
        target_store="neo4j",
        operation_type="source_retracted",
        payload={"bad": "payload"},
        error_count=0,
    )
    repository = FakeOutboxRepository([row])
    worker = OutboxWorker(outbox_repository=repository)

    result = worker.run_once()

    assert result.scanned_count == 1
    assert result.processed_count == 0
    assert result.failed_count == 1
    assert repository.processed == []
    assert "missing required keys" in repository.failed[0]["last_error"]


def test_outbox_worker_main_passes_dry_run(monkeypatch, capsys) -> None:
    class FakeWorker:
        seen_dry_runs: list[bool] = []

        def run_once(self, dry_run: bool = False) -> OutboxWorkerResult:
            self.seen_dry_runs.append(dry_run)
            return OutboxWorkerResult(
                scanned_count=2,
                processed_count=0,
                failed_count=0,
            )

    monkeypatch.setattr(outbox_worker, "OutboxWorker", FakeWorker)

    exit_code = outbox_worker.main(["--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert FakeWorker.seen_dry_runs == [True]
    assert captured.out.strip() == (
        "processed_outbox_rows=0 failed_outbox_rows=0 scanned_outbox_rows=2"
    )
