from __future__ import annotations

from dataclasses import dataclass

from system.outbox_repository import OutboxRepository
from system.source_lifecycle_repository import SourceLifecycleRepository


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

    The no_blocking_rules bundle currently evaluates:
    - no_failed_or_unprocessed_outbox_items through OutboxRepository
    - no_pending_retraction_cascade through SourceLifecycleRepository

    Remaining checks are explicit pass stubs until their repositories are implemented.
    """

    def __init__(
        self,
        outbox_repository: OutboxRepository | None = None,
        source_lifecycle_repository: SourceLifecycleRepository | None = None,
    ) -> None:
        self.outbox_repository = outbox_repository or OutboxRepository()
        self.source_lifecycle_repository = source_lifecycle_repository or SourceLifecycleRepository()

    def evaluate_no_blocking_rules(self, project_id: str) -> HardGateBundleResult:
        checks = (
            self._no_failed_or_unprocessed_outbox_items(project_id),
            self._stub_pass("no_stale_downstream_artifacts"),
            self._no_pending_retraction_cascade(project_id),
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

    def _no_pending_retraction_cascade(self, project_id: str) -> HardGateCheckResult:
        status = self.source_lifecycle_repository.get_project_retraction_cascade_status(project_id)

        if not status.blocked:
            return HardGateCheckResult(
                name="no_pending_retraction_cascade",
                passed=True,
                metadata={
                    "pending_count": status.pending_count,
                    "processing_count": status.processing_count,
                    "failed_count": status.failed_count,
                    "oldest_open_age_seconds": status.oldest_open_age_seconds,
                },
            )

        return HardGateCheckResult(
            name="no_pending_retraction_cascade",
            passed=False,
            reason="project_has_open_retraction_cascade_events",
            metadata={
                "pending_count": status.pending_count,
                "processing_count": status.processing_count,
                "failed_count": status.failed_count,
                "oldest_open_age_seconds": status.oldest_open_age_seconds,
            },
        )

    def _stub_pass(self, name: str) -> HardGateCheckResult:
        return HardGateCheckResult(
            name=name,
            passed=True,
            reason=None,
            metadata={"implementation_status": "stub_pass_pending_repository"},
        )
