from __future__ import annotations

import pytest

import jobs.source_retraction_job as source_retraction_job
from jobs.source_retraction_job import SourceRetractionJob, SourceRetractionJobResult
from system.outbox_repository import IdempotentOutboxWrite, OutboxRow
from system.source_lifecycle_event_repository import SourceLifecycleEvent


class FakeSourceLifecycleEventRepository:
    def __init__(self, events: list[SourceLifecycleEvent]) -> None:
        self.events = events
        self.list_calls: list[int] = []
        self.status_updates: list[dict[str, str | None]] = []

    def list_pending_retraction_events(self, limit: int = 50) -> list[SourceLifecycleEvent]:
        self.list_calls.append(limit)
        return self.events[:limit]

    def claim_pending_retraction_events(self, limit: int = 50) -> list[SourceLifecycleEvent]:
        self.list_calls.append(limit)
        return self.events[:limit]

    def update_processing_status(
        self,
        event_id: str,
        processing_status: str,
        last_error: str | None = None,
    ) -> SourceLifecycleEvent:
        self.status_updates.append(
            {
                "event_id": event_id,
                "processing_status": processing_status,
                "last_error": last_error,
            }
        )
        return SourceLifecycleEvent(
            event_id=event_id,
            project_id="project-1",
            source_id="source-1",
            event_type="retracted",
            processing_status=processing_status,
        )


class FakeOutboxRepository:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.rows: list[dict[str, object]] = []
        self.seen_event_ids: set[str] = set()

    def create_source_retracted_outbox_row(
        self,
        project_id: str,
        source_lifecycle_event_id: str,
        source_id: str,
        event_type: str,
    ) -> IdempotentOutboxWrite:
        if self.fail:
            raise RuntimeError("outbox unavailable")

        inserted = source_lifecycle_event_id not in self.seen_event_ids
        self.seen_event_ids.add(source_lifecycle_event_id)

        row = {
            "project_id": project_id,
            "target_store": "neo4j",
            "operation_type": "source_retracted",
            "payload": {
                "source_lifecycle_event_id": source_lifecycle_event_id,
                "project_id": project_id,
                "source_id": source_id,
                "event_type": event_type,
            },
        }
        if inserted:
            self.rows.append(row)

        return IdempotentOutboxWrite(
            row=OutboxRow(
                outbox_id=f"outbox-{source_lifecycle_event_id}",
                project_id=project_id,
                target_store="neo4j",
                operation_type="source_retracted",
                processed=False,
            ),
            inserted=inserted,
        )


def test_source_retraction_job_no_pending_events() -> None:
    lifecycle_repository = FakeSourceLifecycleEventRepository([])
    outbox_repository = FakeOutboxRepository()

    job = SourceRetractionJob(
        source_lifecycle_event_repository=lifecycle_repository,
        outbox_repository=outbox_repository,
    )

    result = job.run_once(limit=10)

    assert result.scanned_count == 0
    assert result.enqueued_count == 0
    assert result.failed_count == 0
    assert lifecycle_repository.list_calls == [10]
    assert lifecycle_repository.status_updates == []
    assert outbox_repository.rows == []


def test_source_retraction_job_enqueues_outbox_and_marks_processed() -> None:
    event = SourceLifecycleEvent(
        event_id="event-1",
        project_id="project-1",
        source_id="source-1",
        event_type="retracted",
        processing_status="pending",
    )
    lifecycle_repository = FakeSourceLifecycleEventRepository([event])
    outbox_repository = FakeOutboxRepository()

    job = SourceRetractionJob(
        source_lifecycle_event_repository=lifecycle_repository,
        outbox_repository=outbox_repository,
    )

    result = job.run_once()

    assert result.scanned_count == 1
    assert result.enqueued_count == 1
    assert result.failed_count == 0

    assert lifecycle_repository.status_updates == [
        {
            "event_id": "event-1",
            "processing_status": "processed",
            "last_error": None,
        },
    ]

    assert outbox_repository.rows == [
        {
            "project_id": "project-1",
            "target_store": "neo4j",
            "operation_type": "source_retracted",
            "payload": {
                "source_lifecycle_event_id": "event-1",
                "project_id": "project-1",
                "source_id": "source-1",
                "event_type": "retracted",
            },
        }
    ]


def test_source_retraction_job_repeated_scan_does_not_duplicate_source_retracted_outbox() -> None:
    event = SourceLifecycleEvent(
        event_id="event-1",
        project_id="project-1",
        source_id="source-1",
        event_type="retracted",
        processing_status="pending",
    )
    lifecycle_repository = FakeSourceLifecycleEventRepository([event])
    outbox_repository = FakeOutboxRepository()
    job = SourceRetractionJob(
        source_lifecycle_event_repository=lifecycle_repository,
        outbox_repository=outbox_repository,
    )

    first_result = job.run_once()
    second_result = job.run_once()

    assert first_result.enqueued_count == 1
    assert first_result.failed_count == 0
    assert second_result.enqueued_count == 0
    assert second_result.failed_count == 0
    assert len(outbox_repository.rows) == 1
    assert outbox_repository.rows[0]["payload"] == {
        "source_lifecycle_event_id": "event-1",
        "project_id": "project-1",
        "source_id": "source-1",
        "event_type": "retracted",
    }


def test_source_retraction_job_load_count_stays_stable_after_repeat_scan() -> None:
    class BatchLifecycleRepository(FakeSourceLifecycleEventRepository):
        def __init__(self, events: list[SourceLifecycleEvent]) -> None:
            super().__init__(events)
            self.claim_index = 0

        def claim_pending_retraction_events(self, limit: int = 50) -> list[SourceLifecycleEvent]:
            self.list_calls.append(limit)
            batch = self.events[self.claim_index : self.claim_index + limit]
            self.claim_index += len(batch)
            return batch

    events = [
        SourceLifecycleEvent(
            event_id=f"event-{index}",
            project_id="project-1",
            source_id=f"source-{index}",
            event_type="retracted",
            processing_status="pending",
        )
        for index in range(100)
    ]
    lifecycle_repository = BatchLifecycleRepository(events)
    outbox_repository = FakeOutboxRepository()
    job = SourceRetractionJob(
        source_lifecycle_event_repository=lifecycle_repository,
        outbox_repository=outbox_repository,
    )

    first_result = job.run_once(limit=50)
    second_result = job.run_once(limit=50)
    repeat_result = job.run_once(limit=50)

    assert first_result.enqueued_count == 50
    assert second_result.enqueued_count == 50
    assert repeat_result.enqueued_count == 0
    assert len(outbox_repository.rows) == 100


def test_source_retraction_job_marks_failed_when_outbox_enqueue_fails() -> None:
    event = SourceLifecycleEvent(
        event_id="event-1",
        project_id="project-1",
        source_id="source-1",
        event_type="retracted",
        processing_status="pending",
    )
    lifecycle_repository = FakeSourceLifecycleEventRepository([event])
    outbox_repository = FakeOutboxRepository(fail=True)

    job = SourceRetractionJob(
        source_lifecycle_event_repository=lifecycle_repository,
        outbox_repository=outbox_repository,
    )

    result = job.run_once()

    assert result.scanned_count == 1
    assert result.enqueued_count == 0
    assert result.failed_count == 1

    assert lifecycle_repository.status_updates == [
        {
            "event_id": "event-1",
            "processing_status": "failed",
            "last_error": "outbox unavailable",
        },
    ]


def test_source_retraction_job_dry_run_scans_without_mutating() -> None:
    event = SourceLifecycleEvent(
        event_id="event-1",
        project_id="project-1",
        source_id="source-1",
        event_type="retracted",
        processing_status="pending",
    )
    lifecycle_repository = FakeSourceLifecycleEventRepository([event])
    outbox_repository = FakeOutboxRepository()

    job = SourceRetractionJob(
        source_lifecycle_event_repository=lifecycle_repository,
        outbox_repository=outbox_repository,
    )

    result = job.run_once(limit=10, dry_run=True)

    assert result.scanned_count == 1
    assert result.enqueued_count == 0
    assert result.failed_count == 0
    assert lifecycle_repository.list_calls == [10]
    assert lifecycle_repository.status_updates == []
    assert outbox_repository.rows == []


def test_source_retraction_job_validates_limit_through_repository() -> None:
    class RejectingLifecycleRepository(FakeSourceLifecycleEventRepository):
        def list_pending_retraction_events(self, limit: int = 50) -> list[SourceLifecycleEvent]:
            raise ValueError("limit must be between 1 and 50")

        def claim_pending_retraction_events(self, limit: int = 50) -> list[SourceLifecycleEvent]:
            raise ValueError("limit must be between 1 and 50")

    job = SourceRetractionJob(
        source_lifecycle_event_repository=RejectingLifecycleRepository([]),
        outbox_repository=FakeOutboxRepository(),
    )

    with pytest.raises(ValueError, match="limit must be between 1 and 50"):
        job.run_once(limit=99)


def test_source_retraction_job_result_cli_line() -> None:
    result = SourceRetractionJobResult(
        scanned_count=3,
        enqueued_count=2,
        failed_count=1,
    )

    assert result.as_cli_line() == (
        "scanned_source_retraction_events=3 "
        "enqueued_source_retraction_events=2 "
        "failed_source_retraction_events=1"
    )


def test_source_retraction_job_main_runs_once_with_limit(monkeypatch, capsys) -> None:
    class FakeJob:
        seen_calls: list[dict[str, object]] = []

        def run_once(self, limit: int = 50, dry_run: bool = False) -> SourceRetractionJobResult:
            self.seen_calls.append({"limit": limit, "dry_run": dry_run})
            return SourceRetractionJobResult(
                scanned_count=2,
                enqueued_count=1,
                failed_count=0,
            )

    monkeypatch.setattr(source_retraction_job, "SourceRetractionJob", FakeJob)

    exit_code = source_retraction_job.main(["--limit", "7"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert FakeJob.seen_calls == [{"limit": 7, "dry_run": False}]
    assert captured.out.strip() == (
        "scanned_source_retraction_events=2 "
        "enqueued_source_retraction_events=1 "
        "failed_source_retraction_events=0"
    )
    assert captured.err == ""


def test_source_retraction_job_main_passes_dry_run(monkeypatch, capsys) -> None:
    class FakeJob:
        seen_calls: list[dict[str, object]] = []

        def run_once(self, limit: int = 50, dry_run: bool = False) -> SourceRetractionJobResult:
            self.seen_calls.append({"limit": limit, "dry_run": dry_run})
            return SourceRetractionJobResult(
                scanned_count=2,
                enqueued_count=0,
                failed_count=0,
            )

    monkeypatch.setattr(source_retraction_job, "SourceRetractionJob", FakeJob)

    exit_code = source_retraction_job.main(["--limit", "7", "--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert FakeJob.seen_calls == [{"limit": 7, "dry_run": True}]
    assert captured.out.strip() == (
        "scanned_source_retraction_events=2 "
        "enqueued_source_retraction_events=0 "
        "failed_source_retraction_events=0"
    )
    assert captured.err == ""


def test_source_retraction_job_main_reports_failure(monkeypatch, capsys) -> None:
    class FailingJob:
        def run_once(self, limit: int = 50, dry_run: bool = False) -> SourceRetractionJobResult:
            raise RuntimeError(f"failed at limit {limit}")

    monkeypatch.setattr(source_retraction_job, "SourceRetractionJob", FailingJob)

    exit_code = source_retraction_job.main(["--limit", "9"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() == "source_retraction_job_error=failed at limit 9"
