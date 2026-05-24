from __future__ import annotations

from system.hard_gate_repository import HardGateRepository
from system.outbox_repository import OutboxStatus
from system.source_lifecycle_repository import RetractionCascadeStatus


class FakeOutboxRepository:
    def get_project_outbox_status(self, project_id: str) -> OutboxStatus:
        return OutboxStatus(
            project_id=project_id,
            blocked=False,
            unprocessed_count=0,
            failed_count=0,
            oldest_unprocessed_age_seconds=None,
        )


class FakeSourceLifecycleRepository:
    def __init__(self, status: RetractionCascadeStatus) -> None:
        self.status = status
        self.calls: list[str] = []

    def get_project_retraction_cascade_status(self, project_id: str) -> RetractionCascadeStatus:
        self.calls.append(project_id)
        return self.status


def test_hard_gate_repository_passes_when_no_retraction_cascade_open() -> None:
    source_lifecycle_repository = FakeSourceLifecycleRepository(
        RetractionCascadeStatus(
            project_id="project-1",
            blocked=False,
            pending_count=0,
            processing_count=0,
            failed_count=0,
            oldest_open_age_seconds=None,
        )
    )

    repository = HardGateRepository(
        outbox_repository=FakeOutboxRepository(),
        source_lifecycle_repository=source_lifecycle_repository,
    )

    result = repository.evaluate_no_blocking_rules("project-1")

    assert result.passed is True
    assert source_lifecycle_repository.calls == ["project-1"]


def test_hard_gate_repository_blocks_when_retraction_cascade_open() -> None:
    source_lifecycle_repository = FakeSourceLifecycleRepository(
        RetractionCascadeStatus(
            project_id="project-2",
            blocked=True,
            pending_count=2,
            processing_count=1,
            failed_count=1,
            oldest_open_age_seconds=77,
        )
    )

    repository = HardGateRepository(
        outbox_repository=FakeOutboxRepository(),
        source_lifecycle_repository=source_lifecycle_repository,
    )

    result = repository.evaluate_no_blocking_rules("project-2")

    assert result.passed is False
    assert len(result.failed_checks) == 1

    failed = result.failed_checks[0]
    assert failed.name == "no_pending_retraction_cascade"
    assert failed.reason == "project_has_open_retraction_cascade_events"
    assert failed.metadata == {
        "pending_count": 2,
        "processing_count": 1,
        "failed_count": 1,
        "oldest_open_age_seconds": 77,
    }
