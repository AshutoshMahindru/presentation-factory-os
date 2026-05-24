from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from system.audience_profile_validator import AudienceProfileValidator


@dataclass(frozen=True)
class GuardResult:
    name: str
    passed: bool
    reason: str | None = None


class GuardEvaluator:
    """
    Deterministic guard evaluator.

    This baby-step implementation wires the first real schema-backed guard:
    audience_psychology_adequate.

    Other guards are intentionally treated as injectable/contextual and default
    to context-provided booleans. This lets us grow the system without letting
    LLMs advance phases.
    """

    def __init__(self, audience_validator: AudienceProfileValidator | None = None) -> None:
        self.audience_validator = audience_validator or AudienceProfileValidator.from_file()

    def evaluate(self, guard_name: str, context: dict[str, Any]) -> GuardResult:
        if guard_name == "audience_psychology_adequate":
            return self._audience_psychology_adequate(guard_name, context)

        # For now, remaining guards are supplied by deterministic services later.
        # Missing guard context fails closed.
        value = context.get("guards", {}).get(guard_name)
        if value is True:
            return GuardResult(name=guard_name, passed=True)
        return GuardResult(
            name=guard_name,
            passed=False,
            reason=f"Guard {guard_name} was not satisfied by deterministic context.",
        )

    def evaluate_many(self, guard_names: list[str] | tuple[str, ...], context: dict[str, Any]) -> tuple[GuardResult, ...]:
        return tuple(self.evaluate(name, context) for name in guard_names)

    def _audience_psychology_adequate(self, guard_name: str, context: dict[str, Any]) -> GuardResult:
        profile = context.get("project", {}).get("audience_profile")

        if not isinstance(profile, dict):
            return GuardResult(
                name=guard_name,
                passed=False,
                reason="project.audience_profile must be an object.",
            )

        result = self.audience_validator.validate(profile)
        if result.valid:
            return GuardResult(name=guard_name, passed=True)

        return GuardResult(
            name=guard_name,
            passed=False,
            reason="; ".join(result.errors),
        )
