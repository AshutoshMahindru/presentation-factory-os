import os
import subprocess
import time
from uuid import UUID

import pytest

from jobs.outbox_worker import OutboxWorker
from jobs.source_retraction_job import SourceRetractionJob
from system.outbox_repository import OutboxRepository, PendingOutboxRow
from system.source_lifecycle_repository import SourceLifecycleRepository


pytestmark = pytest.mark.skipif(
    os.environ.get("PFOS_RUN_LIVE_TESTS") != "1",
    reason="Live Docker/Postgres load test; set PFOS_RUN_LIVE_TESTS=1",
)

COMPOSE = ["docker", "compose", "-f", "docker-compose.apps.yaml"]
SOURCE_RETRACTION_COUNT = 100
MAX_SUPPORTED_CLAIMS_PER_RETRACTION = 500
SOURCE_RETRACTION_BATCH_SIZE = 50
MAX_INITIAL_BLOCK_TIME_SECONDS = 5
MAX_STANDARD_CASCADE_LATENCY_SECONDS = 30


class SuccessfulSourceRetractionOutboxDrain:
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


def create_project_with_source_retractions() -> str:
    cleanup = psql("DELETE FROM projects WHERE name = 'Source Retraction Load Test Project';")
    assert cleanup.returncode == 0, cleanup.stderr

    sql = f"""
    WITH project AS (
      INSERT INTO projects (name, audience, audience_profile)
      VALUES ('Source Retraction Load Test Project', 'Investment committee', '{{}}'::jsonb)
      RETURNING id
    )
    INSERT INTO source_lifecycle_events (
      project_id,
      source_id,
      event_type,
      source_version,
      classification,
      event_payload,
      hmac_validated,
      processing_status,
      batch_size
    )
    SELECT
      project.id,
      'source-load-' || item_number,
      'retracted',
      'v1',
      'public',
      jsonb_build_object(
        'supported_claim_count', {MAX_SUPPORTED_CLAIMS_PER_RETRACTION},
        'batch_size', {SOURCE_RETRACTION_BATCH_SIZE}
      ),
      TRUE,
      'pending',
      {SOURCE_RETRACTION_BATCH_SIZE}
    FROM project
    CROSS JOIN generate_series(1, {SOURCE_RETRACTION_COUNT}) AS item_number
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

    assert len(project_ids) == SOURCE_RETRACTION_COUNT
    project_id = project_ids[0]
    assert set(project_ids) == {project_id}
    return project_id


def count_project_outbox_rows(project_id: str) -> int:
    result = psql(
        f"""
        SELECT count(*)
        FROM outbox
        WHERE project_id = '{project_id}'
          AND operation_type = 'source_retracted';
        """
    )
    assert result.returncode == 0, result.stderr
    return int(result.stdout.strip())


def count_open_project_outbox_rows(project_id: str) -> int:
    result = psql(
        f"""
        SELECT count(*)
        FROM outbox
        WHERE project_id = '{project_id}'
          AND operation_type = 'source_retracted'
          AND processed = FALSE;
        """
    )
    assert result.returncode == 0, result.stderr
    return int(result.stdout.strip())


def drain_project_source_retraction_outbox(project_id: str) -> int:
    handler = SuccessfulSourceRetractionOutboxDrain()
    worker = OutboxWorker(
        outbox_repository=OutboxRepository(),
        handlers={"source_retracted": handler},
    )

    while True:
        result = worker.run_once(limit=SOURCE_RETRACTION_BATCH_SIZE, project_id=project_id)
        if result.scanned_count == 0:
            break
        assert result.failed_count == 0

    return len(handler.processed_ids)


def test_source_retraction_queue_processes_100_retractions_in_batches_of_50():
    started_at = time.monotonic()
    project_id = create_project_with_source_retractions()

    status_reader = SourceLifecycleRepository()
    initial_status = status_reader.get_project_retraction_cascade_status(project_id)
    initial_block_time_seconds = time.monotonic() - started_at

    assert initial_status.blocked is True
    assert initial_status.pending_count == SOURCE_RETRACTION_COUNT
    assert initial_status.processing_count == 0
    assert initial_status.failed_count == 0
    assert initial_block_time_seconds <= MAX_INITIAL_BLOCK_TIME_SECONDS

    job = SourceRetractionJob()

    first_batch = job.run_once(limit=SOURCE_RETRACTION_BATCH_SIZE)
    assert first_batch.scanned_count == SOURCE_RETRACTION_BATCH_SIZE
    assert first_batch.enqueued_count == SOURCE_RETRACTION_BATCH_SIZE
    assert first_batch.failed_count == 0

    mid_status = status_reader.get_project_retraction_cascade_status(project_id)
    assert mid_status.blocked is True
    assert mid_status.pending_count == SOURCE_RETRACTION_BATCH_SIZE
    assert mid_status.processing_count == 0
    assert mid_status.failed_count == 0

    second_batch = job.run_once(limit=SOURCE_RETRACTION_BATCH_SIZE)
    cascade_latency_seconds = time.monotonic() - started_at

    assert second_batch.scanned_count == SOURCE_RETRACTION_BATCH_SIZE
    assert second_batch.enqueued_count == SOURCE_RETRACTION_BATCH_SIZE
    assert second_batch.failed_count == 0
    assert cascade_latency_seconds <= MAX_STANDARD_CASCADE_LATENCY_SECONDS

    final_status = status_reader.get_project_retraction_cascade_status(project_id)
    assert final_status.blocked is False
    assert final_status.pending_count == 0
    assert final_status.processing_count == 0
    assert final_status.failed_count == 0
    assert count_project_outbox_rows(project_id) == SOURCE_RETRACTION_COUNT

    open_outbox_before_drain = count_open_project_outbox_rows(project_id)
    drained_by_test = drain_project_source_retraction_outbox(project_id)
    assert 0 <= drained_by_test <= SOURCE_RETRACTION_COUNT
    assert drained_by_test <= open_outbox_before_drain
    assert count_open_project_outbox_rows(project_id) == 0
