from __future__ import annotations

from dataclasses import dataclass

from system.blocking_rules_repository import BlockingRulesRepository
from system.outbox_repository import OutboxRepository
from system.source_lifecycle_repository import SourceLifecycleRepository
from system.stale_artifact_repository import StaleArtifactRepository


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

    def as_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "reason": check.reason,
                    "metadata": check.metadata or {},
                }
                for check in self.checks
            ],
            "failed_checks": [
                {
                    "name": check.name,
                    "reason": check.reason,
                    "metadata": check.metadata or {},
                }
                for check in self.failed_checks
            ],
        }


class HardGateRepository:
    """
    Deterministic hard-gate bundle evaluator.

    The no_blocking_rules bundle evaluates:
    - no_failed_or_unprocessed_outbox_items through OutboxRepository
    - no_stale_downstream_artifacts through StaleArtifactRepository
    - no_pending_retraction_cascade through SourceLifecycleRepository
    - no_blocking_rules_table_flags through BlockingRulesRepository
    """

    def __init__(
        self,
        outbox_repository: OutboxRepository | None = None,
        source_lifecycle_repository: SourceLifecycleRepository | None = None,
        stale_artifact_repository: StaleArtifactRepository | None = None,
        blocking_rules_repository: BlockingRulesRepository | None = None,
    ) -> None:
        self.outbox_repository = outbox_repository or OutboxRepository()
        self.source_lifecycle_repository = source_lifecycle_repository or SourceLifecycleRepository()
        self.stale_artifact_repository = stale_artifact_repository or StaleArtifactRepository()
        self.blocking_rules_repository = blocking_rules_repository or BlockingRulesRepository()

    def evaluate_no_blocking_rules(self, project_id: str) -> HardGateBundleResult:
        checks = (
            self._no_failed_or_unprocessed_outbox_items(project_id),
            self._no_stale_downstream_artifacts(project_id),
            self._no_pending_retraction_cascade(project_id),
            self._no_blocking_rules_table_flags(project_id),
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

    def _no_stale_downstream_artifacts(self, project_id: str) -> HardGateCheckResult:
        status = self.stale_artifact_repository.get_project_stale_artifact_status(project_id)

        if not status.blocked:
            return HardGateCheckResult(
                name="no_stale_downstream_artifacts",
                passed=True,
                metadata={
                    "financial_cells_count": status.financial_cells_count,
                    "design_tokens_count": status.design_tokens_count,
                    "total_count": status.total_count,
                },
            )

        return HardGateCheckResult(
            name="no_stale_downstream_artifacts",
            passed=False,
            reason="project_has_stale_downstream_artifacts",
            metadata={
                "financial_cells_count": status.financial_cells_count,
                "design_tokens_count": status.design_tokens_count,
                "total_count": status.total_count,
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

    def _no_blocking_rules_table_flags(self, project_id: str) -> HardGateCheckResult:
        status = self.blocking_rules_repository.get_project_blocking_rules_status(project_id)

        if not status.blocked:
            return HardGateCheckResult(
                name="no_blocking_rules_table_flags",
                passed=True,
                metadata={
                    "blocking_count": status.blocking_count,
                    "warning_count": status.warning_count,
                    "info_count": status.info_count,
                },
            )

        return HardGateCheckResult(
            name="no_blocking_rules_table_flags",
            passed=False,
            reason="project_has_open_blocking_rule_flags",
            metadata={
                "blocking_count": status.blocking_count,
                "warning_count": status.warning_count,
                "info_count": status.info_count,
            },
        )
