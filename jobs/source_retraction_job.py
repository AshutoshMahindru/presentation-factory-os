from __future__ import annotations

import argparse
import sys
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

    def as_cli_line(self) -> str:
        return (
            f"scanned_source_retraction_events={self.scanned_count} "
            f"enqueued_source_retraction_events={self.enqueued_count} "
            f"failed_source_retraction_events={self.failed_count}"
        )


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

    def run_once(self, limit: int = 50, dry_run: bool = False) -> SourceRetractionJobResult:
        events = self.source_lifecycle_event_repository.list_pending_retraction_events(limit=limit)

        scanned_count = len(events)
        if dry_run:
            return SourceRetractionJobResult(
                scanned_count=scanned_count,
                enqueued_count=0,
                failed_count=0,
            )

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one source retraction job pass.")
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum pending retraction lifecycle events to scan, 1-50.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan pending retraction lifecycle events without enqueueing or mutating rows.",
    )
    args = parser.parse_args(argv)

    try:
        result = SourceRetractionJob().run_once(limit=args.limit, dry_run=args.dry_run)
    except Exception as exc:
        print(f"source_retraction_job_error={exc}", file=sys.stderr)
        return 1

    print(result.as_cli_line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
