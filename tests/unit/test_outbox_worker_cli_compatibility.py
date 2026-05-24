from __future__ import annotations

from jobs.outbox_worker import OutboxWorkerResult


def test_outbox_worker_result_cli_line_matches_existing_contract() -> None:
    result = OutboxWorkerResult(
        scanned_count=3,
        processed_count=2,
        failed_count=1,
    )

    assert result.as_cli_line() == (
        "processed_outbox_rows=2 failed_outbox_rows=1 scanned_outbox_rows=3"
    )
