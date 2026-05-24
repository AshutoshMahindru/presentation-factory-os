from __future__ import annotations

from dataclasses import dataclass

from system.outbox_repository import OutboxRepository
from system.source_lifecycle_event_repository import (
    SourceLifecycleEvent,
    SourceLifecycleEventRepository,
)


@dataclass(frozen=True)
class SourceRetractionJobResult:
    scanned_count: int
    enqueued_count: int
    failed_count: int


class SourceRetractionJob:
    """
    Deterministic source retraction worker skeleton.

    The job does not write Neo4j directly. It translates pending retraction
    lifecycle events into Postgres outbox rows. The outbox worker later applies
    idempotent Neo4j side effects.
    """

    def __init__(
        self,
        source_lifecycle_event_repository: SourceLifecycleEventRepository | None = None,
        outbox_repository: OutboxRepository | None = None,
    ) -> None:
        self.source_lifecycle_event_repository = (
            source_lifecycle_event_repository or SourceLifecycleEventRepository()
        )
        self.outbox_repository = outbox_repository or OutboxRepository()

    def run_once(self, limit: int = 50) -> SourceRetractionJobResult:
        events = self.source_lifecycle_event_repository.list_pending_retraction_events(limit=limit)

        scanned_count = len(events)
        enqueued_count = 0
        failed_count = 0

        for event in events:
            try:
                self._process_event(event)
                enqueued_count += 1
            except Exception as exc:
                failed_count += 1
                self.source_lifecycle_event_repository.update_processing_status(
                    event_id=event.event_id,
                    processing_status="failed",
                    last_error=str(exc),
                )

        return SourceRetractionJobResult(
            scanned_count=scanned_count,
            enqueued_count=enqueued_count,
            failed_count=failed_count,
        )

    def _process_event(self, event: SourceLifecycleEvent) -> None:
        self.source_lifecycle_event_repository.update_processing_status(
            event_id=event.event_id,
            processing_status="processing",
        )

        self.outbox_repository.create_outbox_row(
            project_id=event.project_id,
            target_store="neo4j",
            operation_type="source_retracted",
            payload={
                "source_lifecycle_event_id": event.event_id,
                "project_id": event.project_id,
                "source_id": event.source_id,
                "event_type": event.event_type,
            },
        )

        self.source_lifecycle_event_repository.update_processing_status(
            event_id=event.event_id,
            processing_status="processed",
        )
