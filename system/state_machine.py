from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from system.guards import GuardEvaluator, GuardResult


TransitionKind = Literal["forward", "retreat", "reject"]


class StateMachineError(Exception):
    """Base error for state machine failures."""


class InvalidPhaseError(StateMachineError):
    """Raised when a phase is not declared in the state machine spec."""


class InvalidTransitionError(StateMachineError):
    """Raised when a transition is not allowed by the state machine spec."""


class MissingRetreatReasonError(StateMachineError):
    """Raised when a retreat transition is requested without a reason."""


class TerminalPhaseError(StateMachineError):
    """Raised when attempting to transition out of a terminal phase."""


class GuardFailedError(StateMachineError):
    """Raised when one or more transition guards fail."""

    def __init__(self, failed_guards: tuple[GuardResult, ...]) -> None:
        self.failed_guards = failed_guards
        details = "; ".join(
            f"{guard.name}: {guard.reason or 'failed'}" for guard in failed_guards
        )
        super().__init__(f"Transition blocked by guard failure(s): {details}")


@dataclass(frozen=True)
class Transition:
    from_phase: str
    to_phase: str
    kind: TransitionKind
    guards: tuple[str, ...]


class StateMachine:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self.version = str(spec.get("version"))
        self.phases = tuple(spec["phases"])
        self.runtime_rules = spec.get("runtime_rules", {})
        self.transitions = self._load_transitions(spec.get("transitions", {}))

    @classmethod
    def from_yaml(cls, path: str | Path = "docs/08_StateMachine_Spec.yaml") -> "StateMachine":
        spec_path = Path(path)
        if not spec_path.exists():
            raise FileNotFoundError(f"State machine spec not found: {spec_path}")
        spec = yaml.safe_load(spec_path.read_text())
        return cls(spec)

    def _load_transitions(self, transitions: dict[str, list[dict[str, Any]]]) -> dict[tuple[str, str, str], Transition]:
        loaded: dict[tuple[str, str, str], Transition] = {}

        for kind in ("forward", "retreat", "reject"):
            for item in transitions.get(kind, []):
                transition = Transition(
                    from_phase=item["from"],
                    to_phase=item["to"],
                    kind=kind,  # type: ignore[arg-type]
                    guards=tuple(item.get("guards", [])),
                )
                loaded[(transition.from_phase, transition.to_phase, transition.kind)] = transition

        return loaded

    def assert_phase(self, phase: str) -> None:
        if phase not in self.phases:
            raise InvalidPhaseError(f"Unknown phase: {phase}")

    def is_terminal(self, phase: str) -> bool:
        return phase == "rejected" or phase == "exported"

    def get_transition(self, from_phase: str, to_phase: str, kind: TransitionKind) -> Transition:
        self.assert_phase(from_phase)
        self.assert_phase(to_phase)

        if self.is_terminal(from_phase):
            raise TerminalPhaseError(f"Cannot transition out of terminal phase: {from_phase}")

        key = (from_phase, to_phase, kind)
        if key not in self.transitions:
            raise InvalidTransitionError(f"Invalid {kind} transition: {from_phase} -> {to_phase}")

        return self.transitions[key]

    def validate_transition(
        self,
        from_phase: str,
        to_phase: str,
        kind: TransitionKind,
        reason: str | None = None,
    ) -> Transition:
        transition = self.get_transition(from_phase, to_phase, kind)

        if kind == "retreat" and self.runtime_rules.get("retreat_requires_reason", False):
            if not reason or not reason.strip():
                raise MissingRetreatReasonError("Retreat transitions require a non-empty reason.")

        return transition

    def validate_transition_with_guards(
        self,
        from_phase: str,
        to_phase: str,
        kind: TransitionKind,
        context: dict[str, Any],
        reason: str | None = None,
        guard_evaluator: GuardEvaluator | None = None,
    ) -> tuple[Transition, tuple[GuardResult, ...]]:
        transition = self.validate_transition(
            from_phase=from_phase,
            to_phase=to_phase,
            kind=kind,
            reason=reason,
        )

        evaluator = guard_evaluator or GuardEvaluator()
        guard_results = evaluator.evaluate_many(transition.guards, context)
        failed = tuple(result for result in guard_results if not result.passed)

        if failed:
            raise GuardFailedError(failed)

        return transition, guard_results
