from __future__ import annotations

from dataclasses import dataclass

from system.outbox_repository import OutboxRepository


@dataclass(frozen=True)
class HardGateCheckResult:
    name: str
    passed: bool
    reason: str | None = None
    metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class HardGateBundleResult:
    name: str
    passed: bool
    checks: tuple[HardGateCheckResult, ...]

    @property
    def failed_checks(self) -> tuple[HardGateCheckResult, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def reason(self) -> str | None:
        if self.passed:
            return None

        failed = [
            f"{check.name}: {check.reason or 'failed'}"
            for check in self.failed_checks
        ]
        return "; ".join(failed)


class HardGateRepository:
    """
    Deterministic hard-gate bundle evaluator.

    Baby Step 45 makes no_blocking_rules repository-backed for outbox state.
    Other hard-gate checks are explicit pass stubs and should be replaced by
    real repositories in later baby steps.
    """

    def __init__(self, outbox_repository: OutboxRepository | None = None) -> None:
        self.outbox_repository = outbox_repository or OutboxRepository()

    def evaluate_no_blocking_rules(self, project_id: str) -> HardGateBundleResult:
        checks = (
            self._no_failed_or_unprocessed_outbox_items(project_id),
            self._stub_pass("no_stale_downstream_artifacts"),
            self._stub_pass("no_pending_retraction_cascade"),
            self._stub_pass("no_blocking_rules_table_flags"),
        )

        return HardGateBundleResult(
            name="no_blocking_rules",
            passed=all(check.passed for check in checks),
            checks=checks,
        )

    def _no_failed_or_unprocessed_outbox_items(self, project_id: str) -> HardGateCheckResult:
        status = self.outbox_repository.get_project_outbox_status(project_id)

        if not status.blocked:
            return HardGateCheckResult(
                name="no_failed_or_unprocessed_outbox_items",
                passed=True,
                metadata={
                    "unprocessed_count": status.unprocessed_count,
                    "failed_count": status.failed_count,
                    "oldest_unprocessed_age_seconds": status.oldest_unprocessed_age_seconds,
                },
            )

        return HardGateCheckResult(
            name="no_failed_or_unprocessed_outbox_items",
            passed=False,
            reason="project_has_failed_or_unprocessed_outbox_rows",
            metadata={
                "unprocessed_count": status.unprocessed_count,
                "failed_count": status.failed_count,
                "oldest_unprocessed_age_seconds": status.oldest_unprocessed_age_seconds,
            },
        )

    def _stub_pass(self, name: str) -> HardGateCheckResult:
        return HardGateCheckResult(
            name=name,
            passed=True,
            reason=None,
            metadata={"implementation_status": "stub_pass_pending_repository"},
        )
