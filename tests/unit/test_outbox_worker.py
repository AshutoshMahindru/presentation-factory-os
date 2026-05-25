from __future__ import annotations

import jobs.outbox_worker as outbox_worker
from jobs.outbox_worker import Neo4jConnectionConfig, OutboxWorker, OutboxWorkerResult
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


def test_neo4j_project_handler_uses_driver_with_id_property_and_payload_fields() -> None:
    from jobs.outbox_worker import Neo4jProjectNodeHandler

    calls: dict[str, object] = {}

    class FakeQueryResult:
        def consume(self) -> None:
            calls["consumed"] = True

    class FakeTransaction:
        def run(self, query: str, **parameters: object) -> FakeQueryResult:
            calls["query"] = query
            calls["parameters"] = parameters
            return FakeQueryResult()

    class FakeSession:
        def __enter__(self) -> "FakeSession":
            calls["session_entered"] = True
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            calls["session_exited"] = True

        def execute_write(self, callback, **kwargs) -> None:
            calls["write_kwargs"] = kwargs
            callback(FakeTransaction(), **kwargs)

    class FakeDriver:
        def session(self, **options: object) -> FakeSession:
            calls["session_options"] = options
            return FakeSession()

        def close(self) -> None:
            calls["closed"] = True

    def fake_driver_factory(uri: str, auth: tuple[str, str]) -> FakeDriver:
        calls["uri"] = uri
        calls["auth"] = auth
        return FakeDriver()

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

    Neo4jProjectNodeHandler(
        config=Neo4jConnectionConfig(
            uri="bolt://neo4j:7687",
            user="neo4j",
            password="secret",
            database="neo4j",
        ),
        driver_factory=fake_driver_factory,
    )(row)

    assert calls["uri"] == "bolt://neo4j:7687"
    assert calls["auth"] == ("neo4j", "secret")
    assert calls["session_options"] == {"database": "neo4j"}
    assert "MERGE (p:Project {id: $project_id})" in str(calls["query"])
    assert "coalesce($name, p.name)" in str(calls["query"])
    assert "coalesce($current_phase, p.current_phase)" in str(calls["query"])
    assert calls["parameters"] == {
        "project_id": "project-1",
        "name": "Demo Project",
        "current_phase": "strategy",
    }
    assert calls["write_kwargs"] == {
        "project_id": "project-1",
        "name": "Demo Project",
        "current_phase": "strategy",
    }
    assert calls["consumed"] is True
    assert calls["closed"] is True


def test_neo4j_project_handler_reads_connection_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://custom-neo4j:7687")
    monkeypatch.setenv("NEO4J_USER", "custom-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "custom-password")
    monkeypatch.setenv("NEO4J_DATABASE", "custom-db")

    config = Neo4jConnectionConfig.from_env()

    assert config == Neo4jConnectionConfig(
        uri="bolt://custom-neo4j:7687",
        user="custom-user",
        password="custom-password",
        database="custom-db",
    )


def test_neo4j_project_handler_reads_password_from_neo4j_auth(monkeypatch) -> None:
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.setenv("NEO4J_AUTH", "neo4j/auth-password")

    config = Neo4jConnectionConfig.from_env()

    assert config.user == "neo4j"
    assert config.password == "auth-password"


def test_neo4j_project_handler_forced_failure_does_not_open_driver(monkeypatch) -> None:
    from jobs.outbox_worker import Neo4jProjectNodeHandler

    driver_calls: list[tuple[object, ...]] = []

    def fake_driver_factory(*args: object, **kwargs: object) -> object:
        driver_calls.append(args)
        raise AssertionError("driver should not be opened")

    monkeypatch.setenv("PFOS_FORCE_OUTBOX_FAILURE", "1")

    row = PendingOutboxRow(
        outbox_id="outbox-1",
        project_id="project-1",
        target_store="neo4j",
        operation_type="phase_transition_side_effect",
        payload={"project_id": "project-1"},
        error_count=0,
    )

    try:
        Neo4jProjectNodeHandler(driver_factory=fake_driver_factory)(row)
    except RuntimeError as exc:
        assert str(exc) == "Forced outbox operation failure"
    else:
        raise AssertionError("Expected forced outbox operation failure")

    assert driver_calls == []


def test_outbox_worker_marks_failed_when_neo4j_driver_write_raises() -> None:
    from jobs.outbox_worker import Neo4jProjectNodeHandler

    class FailingSession:
        def __enter__(self) -> "FailingSession":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def execute_write(self, callback, **kwargs) -> None:
            raise RuntimeError("neo4j unavailable")

    class FailingDriver:
        def __init__(self) -> None:
            self.closed = False

        def session(self, **options: object) -> FailingSession:
            return FailingSession()

        def close(self) -> None:
            self.closed = True

    driver = FailingDriver()

    def fake_driver_factory(uri: str, auth: tuple[str, str]) -> FailingDriver:
        return driver

    row = PendingOutboxRow(
        outbox_id="outbox-1",
        project_id="project-1",
        target_store="neo4j",
        operation_type="phase_transition_side_effect",
        payload={"project_id": "project-1"},
        error_count=0,
    )
    repository = FakeOutboxRepository([row])
    worker = OutboxWorker(
        outbox_repository=repository,
        handlers={
            "phase_transition_side_effect": Neo4jProjectNodeHandler(
                config=Neo4jConnectionConfig(
                    uri="bolt://neo4j:7687",
                    user="neo4j",
                    password="secret",
                ),
                driver_factory=fake_driver_factory,
            )
        },
    )

    result = worker.run_once()

    assert result.scanned_count == 1
    assert result.processed_count == 0
    assert result.failed_count == 1
    assert repository.processed == []
    assert repository.failed == [
        {"outbox_id": "outbox-1", "last_error": "neo4j unavailable"}
    ]
    assert driver.closed is True


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
