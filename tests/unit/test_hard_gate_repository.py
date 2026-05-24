from __future__ import annotations

from system.hard_gate_repository import HardGateRepository
from system.outbox_repository import OutboxStatus
from system.source_lifecycle_repository import RetractionCascadeStatus


class FakeSourceLifecycleRepository:
    def get_project_retraction_cascade_status(self, project_id: str) -> RetractionCascadeStatus:
        return RetractionCascadeStatus(
            project_id=project_id,
            blocked=False,
            pending_count=0,
            processing_count=0,
            failed_count=0,
            oldest_open_age_seconds=None,
        )


class FakeOutboxRepository:
    def __init__(self, status: OutboxStatus) -> None:
        self.status = status
        self.calls: list[str] = []

    def get_project_outbox_status(self, project_id: str) -> OutboxStatus:
        self.calls.append(project_id)
        return self.status


def test_hard_gate_repository_passes_when_outbox_clean() -> None:
    outbox_repository = FakeOutboxRepository(
        OutboxStatus(
            project_id="project-1",
            blocked=False,
            unprocessed_count=0,
            failed_count=0,
            oldest_unprocessed_age_seconds=None,
        )
    )
    repository = HardGateRepository(
        outbox_repository=outbox_repository,
        source_lifecycle_repository=FakeSourceLifecycleRepository(),
    )

    result = repository.evaluate_no_blocking_rules("project-1")

    assert result.passed is True
    assert result.failed_checks == ()
    assert result.reason() is None
    assert outbox_repository.calls == ["project-1"]
    assert [check.name for check in result.checks] == [
        "no_failed_or_unprocessed_outbox_items",
        "no_stale_downstream_artifacts",
        "no_pending_retraction_cascade",
        "no_blocking_rules_table_flags",
    ]


def test_hard_gate_repository_blocks_when_outbox_blocked() -> None:
    outbox_repository = FakeOutboxRepository(
        OutboxStatus(
            project_id="project-2",
            blocked=True,
            unprocessed_count=3,
            failed_count=1,
            oldest_unprocessed_age_seconds=91,
        )
    )
    repository = HardGateRepository(
        outbox_repository=outbox_repository,
        source_lifecycle_repository=FakeSourceLifecycleRepository(),
    )

    result = repository.evaluate_no_blocking_rules("project-2")

    assert result.passed is False
    assert len(result.failed_checks) == 1

    failed = result.failed_checks[0]
    assert failed.name == "no_failed_or_unprocessed_outbox_items"
    assert failed.reason == "project_has_failed_or_unprocessed_outbox_rows"
    assert failed.metadata == {
        "unprocessed_count": 3,
        "failed_count": 1,
        "oldest_unprocessed_age_seconds": 91,
    }
    assert "project_has_failed_or_unprocessed_outbox_rows" in str(result.reason())
