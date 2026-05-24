from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


APPROVED = "approved"
REJECTED = "rejected"
CHANGES_REQUESTED = "changes_requested"
ABSTAINED = "abstained"


class QuorumError(Exception):
    """Base error for quorum computation."""


class UnknownApprovalPhaseError(QuorumError):
    """Raised when a phase has no approval quorum rule."""


class InvalidApprovalRoleError(QuorumError):
    """Raised when an approval role is not allowed for the phase."""


class InvalidApprovalDecisionError(QuorumError):
    """Raised when an approval decision is not valid."""


@dataclass(frozen=True)
class ApprovalEntry:
    actor_email: str
    role: str
    decision: str


@dataclass(frozen=True)
class QuorumResult:
    phase: str
    quorum_met: bool
    decision_rule: str
    required_count: int
    approved_count: int
    rejected_count: int
    abstained_count: int
    changes_requested_count: int
    missing_roles: dict[str, int]
    blocking_rejection: bool


class ApprovalQuorum:
    VALID_DECISIONS = {APPROVED, REJECTED, CHANGES_REQUESTED, ABSTAINED}

    def __init__(self, rules: dict[str, Any]) -> None:
        self.rules = rules

    @classmethod
    def from_yaml(cls, path: str | Path = "docs/15_Human_Approval_Ledger.yaml") -> "ApprovalQuorum":
        spec_path = Path(path)
        if not spec_path.exists():
            raise FileNotFoundError(f"Approval ledger spec not found: {spec_path}")
        spec = yaml.safe_load(spec_path.read_text())
        return cls(spec["quorum_computation"])

    def evaluate(self, phase: str, entries: list[ApprovalEntry]) -> QuorumResult:
        if phase not in self.rules:
            raise UnknownApprovalPhaseError(f"No approval quorum rule for phase: {phase}")

        rule = self.rules[phase]
        allowed_roles = set(rule.get("allowed_roles", []))
        required_count = int(rule["required_count"])
        decision_rule = rule["decision_rule"]
        minimum_roles = rule.get("minimum_roles", {}) or {}

        counted_entries: list[ApprovalEntry] = []

        for entry in entries:
            if entry.decision not in self.VALID_DECISIONS:
                raise InvalidApprovalDecisionError(f"Invalid approval decision: {entry.decision}")

            if entry.role not in allowed_roles:
                raise InvalidApprovalRoleError(f"Role {entry.role} is not allowed for phase {phase}")

            if entry.decision != ABSTAINED:
                counted_entries.append(entry)

        approved_entries = [e for e in counted_entries if e.decision == APPROVED]
        rejected_entries = [e for e in counted_entries if e.decision == REJECTED]
        changes_requested_entries = [e for e in counted_entries if e.decision == CHANGES_REQUESTED]
        abstained_entries = [e for e in entries if e.decision == ABSTAINED]

        role_counts = Counter(e.role for e in approved_entries)
        missing_roles: dict[str, int] = {}

        for role, minimum in minimum_roles.items():
            current = role_counts.get(role, 0)
            if current < int(minimum):
                missing_roles[role] = int(minimum) - current

        blocking_rejection = bool(rejected_entries or changes_requested_entries)

        if decision_rule == "unanimous":
            quorum_met = (
                len(approved_entries) >= required_count
                and not blocking_rejection
                and not missing_roles
            )
        elif decision_rule == "majority":
            quorum_met = (
                len(approved_entries) >= required_count
                and len(approved_entries) > len(rejected_entries) + len(changes_requested_entries)
                and not missing_roles
            )
        else:
            raise QuorumError(f"Unsupported decision rule: {decision_rule}")

        return QuorumResult(
            phase=phase,
            quorum_met=quorum_met,
            decision_rule=decision_rule,
            required_count=required_count,
            approved_count=len(approved_entries),
            rejected_count=len(rejected_entries),
            abstained_count=len(abstained_entries),
            changes_requested_count=len(changes_requested_entries),
            missing_roles=missing_roles,
            blocking_rejection=blocking_rejection,
        )
