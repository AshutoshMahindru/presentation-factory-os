from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence


REQUIRED_TABLES = (
    "projects",
    "source_lifecycle_events",
    "outbox",
)

TABLE_PRESENCE_SQL = """
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
  AND table_name = ANY(%s)
ORDER BY table_name
"""

SOURCE_LIFECYCLE_GROUP_SQL = """
SELECT
  processing_status,
  event_type,
  count(*)::int AS row_count
FROM source_lifecycle_events
GROUP BY processing_status, event_type
ORDER BY processing_status, event_type
"""

OUTBOX_GROUP_SQL = """
SELECT
  processed,
  error_count,
  target_store,
  operation_type,
  count(*)::int AS row_count
FROM outbox
GROUP BY processed, error_count, target_store, operation_type
ORDER BY processed, error_count, target_store, operation_type
"""

OLDEST_SOURCE_LIFECYCLE_BLOCKING_SQL = """
SELECT
  id,
  project_id,
  source_id,
  event_type,
  processing_status,
  error_count,
  created_at,
  last_error
FROM source_lifecycle_events
WHERE processing_status IN ('pending', 'failed')
ORDER BY created_at ASC
LIMIT 1
"""

OLDEST_OUTBOX_BLOCKING_SQL = """
SELECT
  id,
  project_id,
  target_store,
  operation_type,
  processed,
  error_count,
  created_at,
  last_error
FROM outbox
WHERE processed = FALSE
ORDER BY created_at ASC
LIMIT 1
"""

SMOKE_SQL_STATEMENTS = (
    TABLE_PRESENCE_SQL,
    SOURCE_LIFECYCLE_GROUP_SQL,
    OUTBOX_GROUP_SQL,
    OLDEST_SOURCE_LIFECYCLE_BLOCKING_SQL,
    OLDEST_OUTBOX_BLOCKING_SQL,
)

QueryRows = list[Mapping[str, Any]]
QueryExecutor = Callable[[str, Sequence[Any]], QueryRows]
QueryExecutorFactory = Callable[[str], QueryExecutor]


@dataclass(frozen=True)
class SmokeSnapshot:
    found_tables: tuple[str, ...]
    source_lifecycle_groups: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    outbox_groups: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    oldest_source_lifecycle_event: Mapping[str, Any] | None = None
    oldest_outbox_row: Mapping[str, Any] | None = None

    @property
    def missing_tables(self) -> tuple[str, ...]:
        found = set(self.found_tables)
        return tuple(table for table in REQUIRED_TABLES if table not in found)


def resolve_database_url(
    cli_database_url: str | None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    if cli_database_url:
        return cli_database_url

    source_env = env if env is not None else os.environ
    return source_env.get("DATABASE_URL") or source_env.get("POSTGRES_URL")


def create_psycopg_query_executor(database_url: str) -> QueryExecutor:
    import psycopg
    from psycopg.rows import dict_row

    def execute(sql: str, params: Sequence[Any] = ()) -> QueryRows:
        ensure_select_only(sql)
        with psycopg.connect(
            database_url,
            row_factory=dict_row,
            options="-c default_transaction_read_only=on",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return list(cursor.fetchall())

    return execute


def collect_snapshot(query: QueryExecutor) -> SmokeSnapshot:
    table_rows = execute_select(query, TABLE_PRESENCE_SQL, (list(REQUIRED_TABLES),))
    found_tables = tuple(str(row["table_name"]) for row in table_rows)
    snapshot = SmokeSnapshot(found_tables=found_tables)
    if snapshot.missing_tables:
        return snapshot

    source_groups = tuple(execute_select(query, SOURCE_LIFECYCLE_GROUP_SQL))
    outbox_groups = tuple(execute_select(query, OUTBOX_GROUP_SQL))
    source_blocking_rows = execute_select(query, OLDEST_SOURCE_LIFECYCLE_BLOCKING_SQL)
    outbox_blocking_rows = execute_select(query, OLDEST_OUTBOX_BLOCKING_SQL)

    return SmokeSnapshot(
        found_tables=found_tables,
        source_lifecycle_groups=source_groups,
        outbox_groups=outbox_groups,
        oldest_source_lifecycle_event=source_blocking_rows[0] if source_blocking_rows else None,
        oldest_outbox_row=outbox_blocking_rows[0] if outbox_blocking_rows else None,
    )


def execute_select(
    query: QueryExecutor,
    sql: str,
    params: Sequence[Any] = (),
) -> QueryRows:
    ensure_select_only(sql)
    return query(sql, params)


def ensure_select_only(sql: str) -> None:
    statement = sql.strip()
    first_token = statement.split(maxsplit=1)[0].upper() if statement else ""
    if first_token != "SELECT":
        raise ValueError("Smoke script only permits SELECT statements")


def render_report(snapshot: SmokeSnapshot) -> str:
    lines = ["PFOS Source Lifecycle and Outbox Smoke Report", ""]

    lines.append("Required tables:")
    for table in REQUIRED_TABLES:
        status = "present" if table in snapshot.found_tables else "missing"
        lines.append(f"  {table}: {status}")

    lines.append("")
    lines.append("Source lifecycle events by processing_status and event_type:")
    if snapshot.source_lifecycle_groups:
        for row in snapshot.source_lifecycle_groups:
            lines.append(
                "  "
                + " ".join(
                    [
                        f"processing_status={_format_value(row.get('processing_status'))}",
                        f"event_type={_format_value(row.get('event_type'))}",
                        f"row_count={_format_value(row.get('row_count'))}",
                    ]
                )
            )
    else:
        lines.append("  none")

    lines.append("")
    lines.append("Outbox by processed, error_count, target_store, and operation_type:")
    if snapshot.outbox_groups:
        for row in snapshot.outbox_groups:
            lines.append(
                "  "
                + " ".join(
                    [
                        f"processed={_format_value(row.get('processed'))}",
                        f"error_count={_format_value(row.get('error_count'))}",
                        f"target_store={_format_value(row.get('target_store'))}",
                        f"operation_type={_format_value(row.get('operation_type'))}",
                        f"row_count={_format_value(row.get('row_count'))}",
                    ]
                )
            )
    else:
        lines.append("  none")

    lines.append("")
    lines.append("Oldest pending or failed source_lifecycle_events row:")
    lines.append(_format_optional_row(snapshot.oldest_source_lifecycle_event))

    lines.append("")
    lines.append("Oldest unprocessed or failed outbox row:")
    lines.append(_format_optional_row(snapshot.oldest_outbox_row))

    if snapshot.missing_tables:
        lines.append("")
        lines.append("Smoke status: FAIL missing required tables: " + ", ".join(snapshot.missing_tables))
    else:
        lines.append("")
        lines.append("Smoke status: PASS required tables present")

    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    query_executor_factory: QueryExecutorFactory = create_psycopg_query_executor,
) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only PFOS source lifecycle and outbox operational smoke report."
    )
    parser.add_argument(
        "--database-url",
        help="Postgres database URL. Defaults to DATABASE_URL, then POSTGRES_URL.",
    )
    args = parser.parse_args(argv)

    database_url = resolve_database_url(args.database_url, env)
    if not database_url:
        print("ERROR no database URL available; pass --database-url or set DATABASE_URL or POSTGRES_URL")
        return 2

    try:
        snapshot = collect_snapshot(query_executor_factory(database_url))
    except Exception as exc:
        print(f"ERROR smoke query failed: {exc}")
        return 1

    print(render_report(snapshot))
    return 1 if snapshot.missing_tables else 0


def _format_optional_row(row: Mapping[str, Any] | None) -> str:
    if not row:
        return "  none"

    ordered_keys = (
        "id",
        "project_id",
        "source_id",
        "event_type",
        "processing_status",
        "target_store",
        "operation_type",
        "processed",
        "error_count",
        "created_at",
        "last_error",
    )
    parts = [
        f"{key}={_format_value(row.get(key))}"
        for key in ordered_keys
        if key in row
    ]
    return "  " + " ".join(parts)


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
