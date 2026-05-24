from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts import source_lifecycle_outbox_smoke as smoke


class FakeQueryExecutor:
    def __init__(self, responses: Mapping[str, list[Mapping[str, Any]]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, Sequence[Any]]] = []

    def __call__(self, sql: str, params: Sequence[Any] = ()) -> list[Mapping[str, Any]]:
        self.calls.append((sql, params))
        for marker, rows in self.responses.items():
            if marker in sql:
                return rows
        raise AssertionError(f"unexpected SQL: {sql}")


def test_resolve_database_url_prefers_cli_then_database_url_then_postgres_url() -> None:
    assert smoke.resolve_database_url(
        "postgresql://cli",
        {"DATABASE_URL": "postgresql://database", "POSTGRES_URL": "postgresql://postgres"},
    ) == "postgresql://cli"
    assert smoke.resolve_database_url(
        None,
        {"DATABASE_URL": "postgresql://database", "POSTGRES_URL": "postgresql://postgres"},
    ) == "postgresql://database"
    assert smoke.resolve_database_url(
        None,
        {"POSTGRES_URL": "postgresql://postgres"},
    ) == "postgresql://postgres"


def test_main_returns_nonzero_when_no_database_url_is_available(capsys) -> None:
    exit_code = smoke.main([], env={})

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "no database URL available" in output


def test_collect_snapshot_stops_when_required_tables_are_missing() -> None:
    query = FakeQueryExecutor(
        {
            "information_schema.tables": [
                {"table_name": "projects"},
                {"table_name": "outbox"},
            ]
        }
    )

    snapshot = smoke.collect_snapshot(query)

    assert snapshot.missing_tables == ("source_lifecycle_events",)
    assert len(query.calls) == 1


def test_main_reports_missing_required_tables_and_returns_nonzero(capsys) -> None:
    captured_urls: list[str] = []
    query = FakeQueryExecutor(
        {
            "information_schema.tables": [
                {"table_name": "projects"},
                {"table_name": "outbox"},
            ]
        }
    )

    def factory(database_url: str) -> smoke.QueryExecutor:
        captured_urls.append(database_url)
        return query

    exit_code = smoke.main(
        ["--database-url", "postgresql://operator-url"],
        env={},
        query_executor_factory=factory,
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert captured_urls == ["postgresql://operator-url"]
    assert "source_lifecycle_events: missing" in output
    assert "Smoke status: FAIL missing required tables: source_lifecycle_events" in output


def test_collect_snapshot_and_render_report_include_operational_groups() -> None:
    created_at = datetime(2026, 5, 25, 3, 30, tzinfo=timezone.utc)
    query = FakeQueryExecutor(
        {
            "information_schema.tables": [
                {"table_name": "projects"},
                {"table_name": "source_lifecycle_events"},
                {"table_name": "outbox"},
            ],
            "FROM source_lifecycle_events\nGROUP BY": [
                {
                    "processing_status": "pending",
                    "event_type": "retracted",
                    "row_count": 2,
                },
                {
                    "processing_status": "processed",
                    "event_type": "updated",
                    "row_count": 3,
                },
            ],
            "FROM outbox\nGROUP BY": [
                {
                    "processed": False,
                    "error_count": 1,
                    "target_store": "neo4j",
                    "operation_type": "source_retracted",
                    "row_count": 1,
                }
            ],
            "WHERE processing_status IN ('pending', 'failed')": [
                {
                    "id": "event-1",
                    "project_id": "project-1",
                    "source_id": "source-1",
                    "event_type": "retracted",
                    "processing_status": "pending",
                    "error_count": 0,
                    "created_at": created_at,
                    "last_error": None,
                }
            ],
            "WHERE processed = FALSE": [
                {
                    "id": "outbox-1",
                    "project_id": "project-1",
                    "target_store": "neo4j",
                    "operation_type": "source_retracted",
                    "processed": False,
                    "error_count": 1,
                    "created_at": created_at,
                    "last_error": "neo4j unavailable",
                }
            ],
        }
    )

    snapshot = smoke.collect_snapshot(query)
    report = smoke.render_report(snapshot)

    assert snapshot.missing_tables == ()
    assert "projects: present" in report
    assert "processing_status=pending event_type=retracted row_count=2" in report
    assert (
        "processed=false error_count=1 target_store=neo4j "
        "operation_type=source_retracted row_count=1"
    ) in report
    assert "id=event-1 project_id=project-1 source_id=source-1" in report
    assert "id=outbox-1 project_id=project-1 target_store=neo4j" in report
    assert "created_at=2026-05-25T03:30:00+00:00" in report
    assert "Smoke status: PASS required tables present" in report


def test_all_smoke_sql_is_select_only() -> None:
    forbidden_tokens = (
        " INSERT ",
        " UPDATE ",
        " DELETE ",
        " ALTER ",
        " DROP ",
        " TRUNCATE ",
        " CREATE ",
    )
    for sql in smoke.SMOKE_SQL_STATEMENTS:
        smoke.ensure_select_only(sql)
        padded = f" {sql.upper()} "
        for token in forbidden_tokens:
            assert token not in padded


def test_script_does_not_import_or_invoke_workers() -> None:
    source_text = Path(smoke.__file__).read_text()

    assert "jobs.source_retraction_job" not in source_text
    assert "jobs.outbox_worker" not in source_text
    assert "import jobs" not in source_text
