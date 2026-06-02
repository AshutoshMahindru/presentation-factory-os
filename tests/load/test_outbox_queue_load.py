import os
import subprocess
import time
from uuid import UUID

import pytest

from jobs.outbox_worker import OutboxWorker
from system.outbox_repository import OutboxRepository, PendingOutboxRow


pytestmark = pytest.mark.skipif(
    os.environ.get("PFOS_RUN_LIVE_TESTS") != "1",
    reason="Live Docker/Postgres load test; set PFOS_RUN_LIVE_TESTS=1",
)

COMPOSE = ["docker", "compose", "-f", "docker-compose.apps.yaml"]
OUTBOX_ITEM_COUNT = 50
MAX_DRAIN_TIME_SECONDS_AFTER_RECOVERY = 60


class SuccessfulOutboxDrain:
    def __init__(self) -> None:
        self.processed_ids: list[str] = []

    def __call__(self, row: PendingOutboxRow) -> None:
        self.processed_ids.append(row.outbox_id)


def psql(sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "pfos",
            "-d",
            "pfos",
            "-v",
            "ON_ERROR_STOP=1",
            "-A",
            "-t",
            "-F",
            "|",
            "-c",
            sql,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def create_project_with_outbox_items() -> str:
    cleanup = psql("DELETE FROM projects WHERE name = 'Outbox Load Test Project';")
    assert cleanup.returncode == 0, cleanup.stderr

    sql = f"""
    WITH project AS (
      INSERT INTO projects (name, audience, audience_profile)
      VALUES ('Outbox Load Test Project', 'Investment committee', '{{}}'::jsonb)
      RETURNING id
    )
    INSERT INTO outbox (
      project_id,
      target_store,
      operation_type,
      payload,
      processed,
      error_count,
      last_error
    )
    SELECT
      project.id,
      'neo4j',
      'phase_transition_side_effect',
      jsonb_build_object(
        'project_id', project.id::text,
        'project_name', 'Outbox Load Test Project',
        'to_phase', 'strategy',
        'sequence', item_number
      ),
      FALSE,
      1,
      'transient neo4j outage'
    FROM project
    CROSS JOIN generate_series(1, {OUTBOX_ITEM_COUNT}) AS item_number
    RETURNING project_id;
    """
    result = psql(sql)
    assert result.returncode == 0, result.stderr

    project_ids = []
    for line in result.stdout.splitlines():
        candidate = line.strip()
        try:
            UUID(candidate)
        except ValueError:
            continue
        project_ids.append(candidate)

    assert len(project_ids) == OUTBOX_ITEM_COUNT
    project_id = project_ids[0]
    assert set(project_ids) == {project_id}
    return project_id


def count_open_failed_outbox_rows(project_id: str) -> int:
    result = psql(
        f"""
        SELECT count(*)
        FROM outbox
        WHERE project_id = '{project_id}'
          AND processed = FALSE
          AND error_count > 0;
        """
    )
    assert result.returncode == 0, result.stderr
    return int(result.stdout.strip())


def count_project_outbox_rows(project_id: str) -> int:
    result = psql(
        f"""
        SELECT count(*)
        FROM outbox
        WHERE project_id = '{project_id}';
        """
    )
    assert result.returncode == 0, result.stderr
    return int(result.stdout.strip())


def test_outbox_queue_drains_50_items_within_recovery_sla():
    project_id = create_project_with_outbox_items()
    repository = OutboxRepository()
    initial_status = repository.get_project_outbox_status(project_id)

    assert count_project_outbox_rows(project_id) == OUTBOX_ITEM_COUNT
    assert initial_status.unprocessed_count == OUTBOX_ITEM_COUNT
    assert initial_status.failed_count == OUTBOX_ITEM_COUNT
    assert count_project_outbox_rows(project_id) == OUTBOX_ITEM_COUNT

    handler = SuccessfulOutboxDrain()
    started_at = time.monotonic()
    recovery_result = OutboxWorker(
        outbox_repository=repository,
        handlers={"phase_transition_side_effect": handler},
    ).run_once(limit=OUTBOX_ITEM_COUNT, project_id=project_id)
    drain_time_seconds = time.monotonic() - started_at

    assert recovery_result.scanned_count == OUTBOX_ITEM_COUNT
    assert recovery_result.processed_count == OUTBOX_ITEM_COUNT
    assert recovery_result.failed_count == 0
    assert len(handler.processed_ids) == OUTBOX_ITEM_COUNT
    assert drain_time_seconds <= MAX_DRAIN_TIME_SECONDS_AFTER_RECOVERY

    final_status = repository.get_project_outbox_status(project_id)
    assert final_status.blocked is False
    assert final_status.unprocessed_count == 0
    assert final_status.failed_count == 0
    assert count_open_failed_outbox_rows(project_id) == 0
