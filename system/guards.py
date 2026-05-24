from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

from system.approval_quorum import ApprovalEntry, ApprovalQuorum
from system.audience_profile_validator import AudienceProfileValidator


COMPOSE_FILE = "docker-compose.apps.yaml"


@dataclass(frozen=True)
class GuardResult:
    name: str
    passed: bool
    reason: str | None = None


class ApprovalLedgerRepository:
    """
    Baby-step Postgres-backed approval ledger reader.

    Uses docker compose + psql to stay consistent with the current repository
    pattern. This keeps approval_quorum_met deterministic and prevents phase
    advancement from depending on caller-supplied boolean flags.
    """

    def list_approvals_for_phase(self, project_id: str, phase: str) -> list[ApprovalEntry]:
        sql = f"""
        SELECT actor_email, role, decision
        FROM approval_ledger
        WHERE project_id = '{self._sql(project_id)}'
          AND phase = '{self._sql(phase)}'
        ORDER BY created_at ASC;
        """

        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                COMPOSE_FILE,
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "pfos",
                "-d",
                "pfos",
                "-v",
                "ON_ERROR_STOP=1",
                "-A",
                "-t",
                "-F",
                "|",
                "-c",
                sql,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        entries: list[ApprovalEntry] = []
        for line in result.stdout.splitlines():
            if "|" not in line:
                continue

            actor_email, role, decision = [part.strip() for part in line.split("|")]
            entries.append(
                ApprovalEntry(
                    actor_email=actor_email,
                    role=role,
                    decision=decision,
                )
            )

        return entries

    def _sql(self, value: str) -> str:
        return str(value).replace("'", "''")


class GuardEvaluator:
    """
    Deterministic guard evaluator.

    Schema-backed and repository-backed guards are evaluated directly.
    Remaining baby-step guards are still supplied by deterministic context and
    fail closed when absent.
    """

    def __init__(
        self,
        audience_validator: AudienceProfileValidator | None = None,
        approval_quorum: ApprovalQuorum | None = None,
        approval_ledger_repository: ApprovalLedgerRepository | None = None,
    ) -> None:
        self.audience_validator = audience_validator or AudienceProfileValidator.from_file()
        self.approval_quorum = approval_quorum or ApprovalQuorum.from_yaml()
        self.approval_ledger_repository = approval_ledger_repository or ApprovalLedgerRepository()

    def evaluate(self, guard_name: str, context: dict[str, Any]) -> GuardResult:
        if guard_name == "audience_psychology_adequate":
            return self._audience_psychology_adequate(guard_name, context)

        if guard_name == "approval_quorum_met":
            return self._approval_quorum_met(guard_name, context)

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

    def _approval_quorum_met(self, guard_name: str, context: dict[str, Any]) -> GuardResult:
        project_id = context.get("project", {}).get("project_id")
        transition = context.get("transition", {})
        from_phase = transition.get("from_phase")
        to_phase = transition.get("to_phase")

        if not isinstance(project_id, str) or not project_id.strip():
            return GuardResult(
                name=guard_name,
                passed=False,
                reason="project.project_id is required for Postgres approval quorum evaluation.",
            )

        phase = self._approval_phase_for_transition(from_phase=from_phase, to_phase=to_phase)
        if phase is None:
            return GuardResult(
                name=guard_name,
                passed=False,
                reason="approval_quorum_met requires a phase-completion transition.",
            )

        try:
            entries = self.approval_ledger_repository.list_approvals_for_phase(
                project_id=project_id,
                phase=phase,
            )
            quorum_result = self.approval_quorum.evaluate(phase, entries)
        except Exception as exc:
            return GuardResult(
                name=guard_name,
                passed=False,
                reason=f"Postgres approval quorum evaluation failed: {exc}",
            )

        if quorum_result.quorum_met:
            return GuardResult(name=guard_name, passed=True)

        return GuardResult(
            name=guard_name,
            passed=False,
            reason=(
                "approval quorum not met for phase "
                f"{phase}: required_count={quorum_result.required_count}, "
                f"approved_count={quorum_result.approved_count}, "
                f"rejected_count={quorum_result.rejected_count}, "
                f"changes_requested_count={quorum_result.changes_requested_count}, "
                f"missing_roles={quorum_result.missing_roles}, "
                f"blocking_rejection={quorum_result.blocking_rejection}"
            ),
        )

    def _approval_phase_for_transition(self, from_phase: Any, to_phase: Any) -> str | None:
        if from_phase == "approved" and to_phase == "exported":
            return "review"

        if from_phase in {"intake", "strategy", "financial_model", "review"}:
            return str(from_phase)

        return None
