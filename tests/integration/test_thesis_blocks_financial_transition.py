from __future__ import annotations

import pytest

from system.guards import GuardEvaluator
from system.hard_gate_repository import HardGateBundleResult, HardGateCheckResult
from system.state_machine import GuardFailedError, StateMachine


class FakeHardGateRepository:
    def evaluate_no_blocking_rules(self, project_id: str) -> HardGateBundleResult:
        assert project_id == "project-1"
        return HardGateBundleResult(
            name="no_blocking_rules",
            passed=False,
            checks=(
                HardGateCheckResult(
                    name="no_stale_downstream_artifacts",
                    passed=False,
                    reason="project_has_stale_downstream_artifacts",
                    metadata={
                        "financial_cells_count": 1,
                        "design_tokens_count": 0,
                        "total_count": 1,
                    },
                ),
            ),
        )


def test_stale_financial_cells_block_financial_model_to_narrative_transition() -> None:
    state_machine = StateMachine.from_yaml()
    evaluator = GuardEvaluator(
        audience_validator=object(),
        hard_gate_repository=FakeHardGateRepository(),  # type: ignore[arg-type]
    )

    with pytest.raises(GuardFailedError) as exc:
        state_machine.validate_transition_with_guards(
            "financial_model",
            "narrative",
            "forward",
            context={
                "project": {"project_id": "project-1"},
                "guards": {
                    "rubric_above_4_0": True,
                    "model_validated": True,
                    "no_unsupported_financial_claims": True,
                    "no_blocking_rules": True,
                },
            },
            guard_evaluator=evaluator,
        )

    failed = exc.value.failed_guards
    assert [guard.name for guard in failed] == ["no_blocking_rules"]
    assert "project_has_stale_downstream_artifacts" in str(failed[0].reason)
