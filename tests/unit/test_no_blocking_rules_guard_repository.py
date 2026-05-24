from __future__ import annotations

from system.guards import GuardEvaluator
from system.hard_gate_repository import HardGateBundleResult, HardGateCheckResult


class FakeHardGateRepository:
    def __init__(self, result: HardGateBundleResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def evaluate_no_blocking_rules(self, project_id: str) -> HardGateBundleResult:
        self.calls.append(project_id)
        return self.result


def test_no_blocking_rules_guard_uses_hard_gate_repository_pass() -> None:
    hard_gate_repository = FakeHardGateRepository(
        HardGateBundleResult(
            name="no_blocking_rules",
            passed=True,
            checks=(
                HardGateCheckResult(
                    name="no_failed_or_unprocessed_outbox_items",
                    passed=True,
                ),
            ),
        )
    )

    evaluator = GuardEvaluator(
        audience_validator=object(),  # not used
        hard_gate_repository=hard_gate_repository,
    )

    result = evaluator.evaluate(
        "no_blocking_rules",
        {
            "project": {"project_id": "project-1"},
            "guards": {"no_blocking_rules": False},
        },
    )

    assert result.passed is True
    assert hard_gate_repository.calls == ["project-1"]


def test_no_blocking_rules_guard_uses_hard_gate_repository_failure() -> None:
    hard_gate_repository = FakeHardGateRepository(
        HardGateBundleResult(
            name="no_blocking_rules",
            passed=False,
            checks=(
                HardGateCheckResult(
                    name="no_failed_or_unprocessed_outbox_items",
                    passed=False,
                    reason="project_has_failed_or_unprocessed_outbox_rows",
                ),
            ),
        )
    )

    evaluator = GuardEvaluator(
        audience_validator=object(),  # not used
        hard_gate_repository=hard_gate_repository,
    )

    result = evaluator.evaluate(
        "no_blocking_rules",
        {
            "project": {"project_id": "project-2"},
            "guards": {"no_blocking_rules": True},
        },
    )

    assert result.passed is False
    assert "project_has_failed_or_unprocessed_outbox_rows" in str(result.reason)
    assert hard_gate_repository.calls == ["project-2"]


def test_no_blocking_rules_guard_requires_project_id() -> None:
    evaluator = GuardEvaluator(audience_validator=object())

    result = evaluator.evaluate("no_blocking_rules", {"project": {}, "guards": {}})

    assert result.passed is False
    assert "project.project_id is required" in str(result.reason)
