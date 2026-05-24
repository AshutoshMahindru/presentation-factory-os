from __future__ import annotations

from system.outbox_repository import OutboxRepository, OutboxStatus


class FakeResult:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_outbox_repository_reports_clean_project() -> None:
    repository = OutboxRepository()

    def fake_psql(sql: str) -> FakeResult:
        return FakeResult("0|0|\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    status = repository.get_project_outbox_status("project-1")

    assert status == OutboxStatus(
        project_id="project-1",
        blocked=False,
        unprocessed_count=0,
        failed_count=0,
        oldest_unprocessed_age_seconds=None,
    )


def test_outbox_repository_reports_unprocessed_rows_as_blocking() -> None:
    repository = OutboxRepository()

    def fake_psql(sql: str) -> FakeResult:
        return FakeResult("2|0|31\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    status = repository.get_project_outbox_status("project-2")

    assert status.blocked is True
    assert status.unprocessed_count == 2
    assert status.failed_count == 0
    assert status.oldest_unprocessed_age_seconds == 31


def test_outbox_repository_reports_failed_rows_as_blocking() -> None:
    repository = OutboxRepository()

    def fake_psql(sql: str) -> FakeResult:
        return FakeResult("2|1|45\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    status = repository.get_project_outbox_status("project-3")

    assert status.blocked is True
    assert status.unprocessed_count == 2
    assert status.failed_count == 1
    assert status.oldest_unprocessed_age_seconds == 45


def test_project_has_blocking_outbox_rows_returns_legacy_tuple() -> None:
    repository = OutboxRepository()

    def fake_status(project_id: str) -> OutboxStatus:
        return OutboxStatus(
            project_id=project_id,
            blocked=True,
            unprocessed_count=3,
            failed_count=1,
            oldest_unprocessed_age_seconds=12,
        )

    repository.get_project_outbox_status = fake_status  # type: ignore[method-assign]

    blocked, count = repository.project_has_blocking_outbox_rows("project-4")

    assert blocked is True
    assert count == 4


def test_outbox_repository_sql_is_project_scoped_and_uses_outbox_table() -> None:
    repository = OutboxRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult("0|0|\n")

    repository._psql = fake_psql  # type: ignore[method-assign]
    repository.get_project_outbox_status("project-with-'quote")

    assert "FROM outbox" in captured["sql"]
    assert "project_id = 'project-with-''quote'" in captured["sql"]
    assert "processed = FALSE" in captured["sql"]
    assert "error_count > 0" in captured["sql"]


def test_outbox_repository_creates_outbox_row() -> None:
    from system.outbox_repository import OutboxRepository

    repository = OutboxRepository()
    captured: dict[str, str] = {}

    class FakeResult:
        returncode = 0
        stdout = "outbox-1|project-1|neo4j|source_retracted|f\n"
        stderr = ""

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult()

    repository._psql = fake_psql  # type: ignore[method-assign]

    row = repository.create_outbox_row(
        project_id="project-1",
        target_store="neo4j",
        operation_type="source_retracted",
        payload={"source_id": "source-1"},
    )

    assert row.outbox_id == "outbox-1"
    assert row.project_id == "project-1"
    assert row.target_store == "neo4j"
    assert row.operation_type == "source_retracted"
    assert row.processed is False

    assert "INSERT INTO outbox" in captured["sql"]
    assert "'source_retracted'" in captured["sql"]
    assert '"source_id": "source-1"' in captured["sql"]


def test_outbox_repository_lists_unprocessed_rows() -> None:
    from system.outbox_repository import OutboxRepository

    repository = OutboxRepository()
    captured: dict[str, str] = {}

    class FakeResult:
        returncode = 0
        stdout = 'outbox-1|project-1|neo4j|source_retracted|{"source_id":"source-1"}|0\n'
        stderr = ""

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult()

    repository._psql = fake_psql  # type: ignore[method-assign]

    rows = repository.list_unprocessed_rows(target_store="neo4j", limit=10)

    assert len(rows) == 1
    assert rows[0].outbox_id == "outbox-1"
    assert rows[0].project_id == "project-1"
    assert rows[0].target_store == "neo4j"
    assert rows[0].operation_type == "source_retracted"
    assert rows[0].payload == {"source_id": "source-1"}
    assert rows[0].error_count == 0

    assert "processed = FALSE" in captured["sql"]
    assert "target_store = 'neo4j'" in captured["sql"]
    assert "LIMIT 10" in captured["sql"]


def test_outbox_repository_rejects_invalid_list_limit() -> None:
    from system.outbox_repository import OutboxRepository

    repository = OutboxRepository()

    import pytest

    with pytest.raises(ValueError, match="limit must be between 1 and 50"):
        repository.list_unprocessed_rows(limit=99)


def test_outbox_repository_marks_processed() -> None:
    from system.outbox_repository import OutboxRepository

    repository = OutboxRepository()
    captured: dict[str, str] = {}

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult()

    repository._psql = fake_psql  # type: ignore[method-assign]

    repository.mark_processed("outbox-1")

    assert "UPDATE outbox" in captured["sql"]
    assert "processed = TRUE" in captured["sql"]
    assert "processed_at = now()" in captured["sql"]
    assert "id = 'outbox-1'" in captured["sql"]


def test_outbox_repository_marks_failed() -> None:
    from system.outbox_repository import OutboxRepository

    repository = OutboxRepository()
    captured: dict[str, str] = {}

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult()

    repository._psql = fake_psql  # type: ignore[method-assign]

    repository.mark_failed("outbox-1", "neo4j unavailable")

    assert "UPDATE outbox" in captured["sql"]
    assert "error_count = LEAST(error_count + 1, 5)" in captured["sql"]
    assert "last_error = 'neo4j unavailable'" in captured["sql"]
    assert "id = 'outbox-1'" in captured["sql"]


def test_outbox_repository_skips_rows_at_retry_ceiling() -> None:
    from system.outbox_repository import OutboxRepository

    repository = OutboxRepository()
    captured: dict[str, str] = {}

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult()

    repository._psql = fake_psql  # type: ignore[method-assign]
    repository.list_unprocessed_rows(target_store="neo4j", limit=10)

    assert "error_count < 5" in captured["sql"]


def test_outbox_repository_mark_failed_caps_error_count() -> None:
    from system.outbox_repository import OutboxRepository

    repository = OutboxRepository()
    captured: dict[str, str] = {}

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult()

    repository._psql = fake_psql  # type: ignore[method-assign]
    repository.mark_failed("outbox-1", "failure")

    assert "LEAST(error_count + 1, 5)" in captured["sql"]


def test_outbox_repository_lists_project_rows() -> None:
    from system.outbox_repository import OutboxRepository

    repository = OutboxRepository()
    captured: dict[str, str] = {}

    class FakeResult:
        returncode = 0
        stdout = 'outbox-1|project-1|neo4j|source_retracted|{"source_id":"source-1"}|0\n'
        stderr = ""

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult()

    repository._psql = fake_psql  # type: ignore[method-assign]

    rows = repository.list_project_rows("project-1")

    assert len(rows) == 1
    assert rows[0].project_id == "project-1"
    assert rows[0].operation_type == "source_retracted"
    assert rows[0].payload == {"source_id": "source-1"}

    assert "FROM outbox" in captured["sql"]
    assert "WHERE project_id = 'project-1'" in captured["sql"]


def test_outbox_repository_lists_unprocessed_rows_with_project_scope() -> None:
    from system.outbox_repository import OutboxRepository

    repository = OutboxRepository()
    captured: dict[str, str] = {}

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult()

    repository._psql = fake_psql  # type: ignore[method-assign]

    repository.list_unprocessed_rows(
        target_store="neo4j",
        limit=10,
        project_id="project-1",
    )

    assert "target_store = 'neo4j'" in captured["sql"]
    assert "project_id = 'project-1'" in captured["sql"]
    assert "error_count < 5" in captured["sql"]
