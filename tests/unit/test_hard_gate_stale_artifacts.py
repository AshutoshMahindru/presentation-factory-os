from __future__ import annotations

from system.blocking_rules_repository import BlockingRulesStatus
from system.hard_gate_repository import HardGateRepository
from system.outbox_repository import OutboxStatus
from system.source_lifecycle_repository import RetractionCascadeStatus
from system.stale_artifact_repository import StaleArtifactStatus


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
    def get_project_retraction_cascade_status(self, project_id: str) -> RetractionCascadeStatus:
        return RetractionCascadeStatus(
            project_id=project_id,
            blocked=False,
            pending_count=0,
            processing_count=0,
            failed_count=0,
            oldest_open_age_seconds=None,
        )


class FakeStaleArtifactRepository:
    def __init__(self, status: StaleArtifactStatus) -> None:
        self.status = status
        self.calls: list[str] = []

    def get_project_stale_artifact_status(self, project_id: str) -> StaleArtifactStatus:
        self.calls.append(project_id)
        return self.status



class FakeBlockingRulesRepository:
    def get_project_blocking_rules_status(self, project_id: str) -> BlockingRulesStatus:
        return BlockingRulesStatus(
            project_id=project_id,
            blocked=False,
            blocking_count=0,
            warning_count=0,
            info_count=0,
        )


def test_hard_gate_repository_passes_when_no_stale_artifacts() -> None:
    stale_artifact_repository = FakeStaleArtifactRepository(
        StaleArtifactStatus(
            project_id="project-1",
            blocked=False,
            financial_cells_count=0,
            design_tokens_count=0,
            total_count=0,
        )
    )

    repository = HardGateRepository(
        outbox_repository=FakeOutboxRepository(),
        source_lifecycle_repository=FakeSourceLifecycleRepository(),
        stale_artifact_repository=stale_artifact_repository,
        blocking_rules_repository=FakeBlockingRulesRepository(),
    )

    result = repository.evaluate_no_blocking_rules("project-1")

    assert result.passed is True
    assert stale_artifact_repository.calls == ["project-1"]


def test_hard_gate_repository_blocks_when_stale_artifacts_exist() -> None:
    stale_artifact_repository = FakeStaleArtifactRepository(
        StaleArtifactStatus(
            project_id="project-2",
            blocked=True,
            financial_cells_count=2,
            design_tokens_count=3,
            total_count=5,
        )
    )

    repository = HardGateRepository(
        outbox_repository=FakeOutboxRepository(),
        source_lifecycle_repository=FakeSourceLifecycleRepository(),
        stale_artifact_repository=stale_artifact_repository,
        blocking_rules_repository=FakeBlockingRulesRepository(),
    )

    result = repository.evaluate_no_blocking_rules("project-2")

    assert result.passed is False
    assert len(result.failed_checks) == 1

    failed = result.failed_checks[0]
    assert failed.name == "no_stale_downstream_artifacts"
    assert failed.reason == "project_has_stale_downstream_artifacts"
    assert failed.metadata == {
        "financial_cells_count": 2,
        "design_tokens_count": 3,
        "total_count": 5,
    }
