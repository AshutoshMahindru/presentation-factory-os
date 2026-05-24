from __future__ import annotations

from system.blocking_rules_repository import BlockingRulesStatus
from system.hard_gate_repository import HardGateRepository
from system.outbox_repository import OutboxStatus
from system.source_lifecycle_repository import RetractionCascadeStatus
from system.stale_artifact_repository import StaleArtifactStatus


class FakeOutboxRepository:
    def get_project_outbox_status(self, project_id: str) -> OutboxStatus:
        return OutboxStatus(project_id, False, 0, 0, None)


class FakeSourceLifecycleRepository:
    def get_project_retraction_cascade_status(self, project_id: str) -> RetractionCascadeStatus:
        return RetractionCascadeStatus(project_id, False, 0, 0, 0, None)


class FakeStaleArtifactRepository:
    def get_project_stale_artifact_status(self, project_id: str) -> StaleArtifactStatus:
        return StaleArtifactStatus(project_id, False, 0, 0, 0)


class FakeBlockingRulesRepository:
    def __init__(self, status: BlockingRulesStatus) -> None:
        self.status = status
        self.calls: list[str] = []

    def get_project_blocking_rules_status(self, project_id: str) -> BlockingRulesStatus:
        self.calls.append(project_id)
        return self.status


def make_repository(blocking_rules_repository: FakeBlockingRulesRepository) -> HardGateRepository:
    return HardGateRepository(
        outbox_repository=FakeOutboxRepository(),
        source_lifecycle_repository=FakeSourceLifecycleRepository(),
        stale_artifact_repository=FakeStaleArtifactRepository(),
        blocking_rules_repository=blocking_rules_repository,
    )


def test_hard_gate_repository_passes_when_no_blocking_rule_flags() -> None:
    blocking_rules_repository = FakeBlockingRulesRepository(
        BlockingRulesStatus("project-1", False, 0, 2, 1)
    )
    repository = make_repository(blocking_rules_repository)

    result = repository.evaluate_no_blocking_rules("project-1")

    assert result.passed is True
    assert blocking_rules_repository.calls == ["project-1"]


def test_hard_gate_repository_blocks_when_blocking_rule_flags_exist() -> None:
    blocking_rules_repository = FakeBlockingRulesRepository(
        BlockingRulesStatus("project-2", True, 2, 1, 0)
    )
    repository = make_repository(blocking_rules_repository)

    result = repository.evaluate_no_blocking_rules("project-2")

    assert result.passed is False
    assert len(result.failed_checks) == 1

    failed = result.failed_checks[0]
    assert failed.name == "no_blocking_rules_table_flags"
    assert failed.reason == "project_has_open_blocking_rule_flags"
    assert failed.metadata == {
        "blocking_count": 2,
        "warning_count": 1,
        "info_count": 0,
    }


def test_hard_gate_bundle_payload_has_normalized_shape() -> None:
    blocking_rules_repository = FakeBlockingRulesRepository(
        BlockingRulesStatus("project-3", True, 1, 0, 0)
    )
    repository = make_repository(blocking_rules_repository)

    payload = repository.evaluate_no_blocking_rules("project-3").as_payload()

    assert payload["name"] == "no_blocking_rules"
    assert payload["passed"] is False
    assert isinstance(payload["checks"], list)
    assert isinstance(payload["failed_checks"], list)
    assert payload["failed_checks"][0]["name"] == "no_blocking_rules_table_flags"
