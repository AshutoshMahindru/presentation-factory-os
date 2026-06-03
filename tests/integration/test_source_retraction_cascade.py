from __future__ import annotations

from dataclasses import dataclass

from deck_builder.export_gate import ExportGate
from jobs.source_retraction_job import SourceRetractionJob
from system.outbox_repository import IdempotentOutboxWrite, OutboxRow
from system.source_lifecycle_event_repository import SourceLifecycleEvent


@dataclass
class MemoryLifecycleRepository:
    events: list[SourceLifecycleEvent]

    def __post_init__(self) -> None:
        self.status_updates: list[tuple[str, str, str | None]] = []

    def claim_pending_retraction_events(self, limit: int = 50) -> list[SourceLifecycleEvent]:
        pending = [event for event in self.events if event.processing_status == "pending"][:limit]
        claimed: list[SourceLifecycleEvent] = []
        for event in pending:
            claimed_event = SourceLifecycleEvent(
                event_id=event.event_id,
                project_id=event.project_id,
                source_id=event.source_id,
                event_type=event.event_type,
                processing_status="processing",
            )
            self._replace_event(claimed_event)
            claimed.append(claimed_event)
        return claimed

    def list_pending_retraction_events(self, limit: int = 50) -> list[SourceLifecycleEvent]:
        return [event for event in self.events if event.processing_status == "pending"][:limit]

    def update_processing_status(
        self,
        event_id: str,
        processing_status: str,
        last_error: str | None = None,
    ) -> SourceLifecycleEvent:
        current = next(event for event in self.events if event.event_id == event_id)
        updated = SourceLifecycleEvent(
            event_id=current.event_id,
            project_id=current.project_id,
            source_id=current.source_id,
            event_type=current.event_type,
            processing_status=processing_status,
        )
        self._replace_event(updated)
        self.status_updates.append((event_id, processing_status, last_error))
        return updated

    def _replace_event(self, replacement: SourceLifecycleEvent) -> None:
        self.events = [
            replacement if event.event_id == replacement.event_id else event
            for event in self.events
        ]


class MemoryOutboxRepository:
    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []

    def create_source_retracted_outbox_row(
        self,
        project_id: str,
        source_lifecycle_event_id: str,
        source_id: str,
        event_type: str,
    ) -> IdempotentOutboxWrite:
        if event_type != "retracted":
            raise ValueError("source retraction cascades only accept retracted events")

        row = OutboxRow(
            outbox_id=f"outbox-{source_lifecycle_event_id}",
            project_id=project_id,
            target_store="neo4j",
            operation_type="source_retracted",
            processed=False,
        )
        already_present = any(
            existing["source_lifecycle_event_id"] == source_lifecycle_event_id
            for existing in self.rows
        )
        if not already_present:
            self.rows.append(
                {
                    "outbox_id": row.outbox_id,
                    "project_id": project_id,
                    "source_lifecycle_event_id": source_lifecycle_event_id,
                    "source_id": source_id,
                    "operation_type": row.operation_type,
                }
            )

        return IdempotentOutboxWrite(row=row, inserted=not already_present)


def test_source_retraction_cascade_enqueues_outbox_and_blocks_export_until_drained() -> None:
    lifecycle_repository = MemoryLifecycleRepository(
        events=[
            SourceLifecycleEvent(
                event_id="event-1",
                project_id="project-147",
                source_id="source-withdrawn",
                event_type="retracted",
                processing_status="pending",
            )
        ]
    )
    outbox_repository = MemoryOutboxRepository()

    job_result = SourceRetractionJob(
        source_lifecycle_event_repository=lifecycle_repository,  # type: ignore[arg-type]
        outbox_repository=outbox_repository,  # type: ignore[arg-type]
    ).run_once(limit=50)

    assert job_result.scanned_count == 1
    assert job_result.enqueued_count == 1
    assert job_result.failed_count == 0
    assert lifecycle_repository.status_updates == [("event-1", "processed", None)]
    assert outbox_repository.rows == [
        {
            "outbox_id": "outbox-event-1",
            "project_id": "project-147",
            "source_lifecycle_event_id": "event-1",
            "source_id": "source-withdrawn",
            "operation_type": "source_retracted",
        }
    ]

    blocked = ExportGate().evaluate(
        {
            "slides": [],
            "financial_validation_status": "validated",
            "unsupported_financial_claim_count": 0,
            "financial_cells": {},
            "artifacts": [],
            "pending_source_retraction_count": 0,
            "unprocessed_outbox_count": len(outbox_repository.rows),
        }
    )
    assert blocked.export_allowed is False
    assert blocked.blocking_reasons == ("Cross-store side effects must be drained before export.",)

    drained = ExportGate().evaluate(
        {
            "slides": [],
            "financial_validation_status": "validated",
            "unsupported_financial_claim_count": 0,
            "financial_cells": {},
            "artifacts": [],
            "pending_source_retraction_count": 0,
            "unprocessed_outbox_count": 0,
        }
    )
    assert drained.export_allowed is True


def test_source_retraction_cascade_dry_run_does_not_mutate_events_or_outbox() -> None:
    lifecycle_repository = MemoryLifecycleRepository(
        events=[
            SourceLifecycleEvent(
                event_id="event-2",
                project_id="project-147",
                source_id="source-withdrawn",
                event_type="retracted",
                processing_status="pending",
            )
        ]
    )
    outbox_repository = MemoryOutboxRepository()

    job_result = SourceRetractionJob(
        source_lifecycle_event_repository=lifecycle_repository,  # type: ignore[arg-type]
        outbox_repository=outbox_repository,  # type: ignore[arg-type]
    ).run_once(limit=50, dry_run=True)

    assert job_result.scanned_count == 1
    assert job_result.enqueued_count == 0
    assert job_result.failed_count == 0
    assert lifecycle_repository.events[0].processing_status == "pending"
    assert lifecycle_repository.status_updates == []
    assert outbox_repository.rows == []
