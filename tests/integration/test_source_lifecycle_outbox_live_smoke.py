from __future__ import annotations

import os
import subprocess
from typing import Any

import pytest

from scripts.source_lifecycle_outbox_smoke import create_psycopg_query_executor


LIVE_DATABASE_URL_ENV = "PFOS_LIVE_DATABASE_URL"


def test_source_lifecycle_outbox_smoke_target_runs_read_only_against_live_postgres() -> None:
    database_url = os.environ.get(LIVE_DATABASE_URL_ENV)
    if not database_url:
        pytest.skip(f"{LIVE_DATABASE_URL_ENV} is not set")

    query = create_psycopg_query_executor(database_url)
    before_counts = queue_counts(query)

    result = subprocess.run(
        ["make", "smoke-source-lifecycle-outbox"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env={**os.environ, "DATABASE_URL": database_url},
    )

    after_counts = queue_counts(query)

    assert result.returncode == 0, result.stderr
    assert "PFOS Source Lifecycle and Outbox Smoke Report" in result.stdout
    assert "Smoke status: PASS required tables present" in result.stdout
    assert after_counts == before_counts


def queue_counts(query: Any) -> dict[str, int]:
    rows = query(
        """
        SELECT 'source_lifecycle_events' AS table_name, count(*)::int AS row_count
        FROM source_lifecycle_events
        UNION ALL
        SELECT 'outbox' AS table_name, count(*)::int AS row_count
        FROM outbox
        ORDER BY table_name
        """,
        (),
    )
    return {str(row["table_name"]): int(row["row_count"]) for row in rows}
