from __future__ import annotations

from system.approval_quorum import ApprovalEntry, ApprovalQuorum
from system.guards import GuardEvaluator


class FakeApprovalLedgerRepository:
    def __init__(self, entries: list[ApprovalEntry]) -> None:
        self.entries = entries
        self.calls: list[tuple[str, str]] = []

    def list_approvals_for_phase(self, project_id: str, phase: str) -> list[ApprovalEntry]:
        self.calls.append((project_id, phase))
        return self.entries


def make_evaluator(entries: list[ApprovalEntry]) -> tuple[GuardEvaluator, FakeApprovalLedgerRepository]:
    repository = FakeApprovalLedgerRepository(entries)
    evaluator = GuardEvaluator(
        audience_validator=object(),  # not used by these tests
        approval_quorum=ApprovalQuorum.from_yaml(),
        approval_ledger_repository=repository,
    )
    return evaluator, repository


def test_approval_quorum_guard_reads_ledger_even_when_context_flag_false() -> None:
    evaluator, repository = make_evaluator(
        [
            ApprovalEntry(
                actor_email="partner@example.com",
                role="partner",
                decision="approved",
            ),
            ApprovalEntry(
                actor_email="ic@example.com",
                role="ic_member",
                decision="approved",
            ),
        ]
    )

    result = evaluator.evaluate(
        "approval_quorum_met",
        {
            "project": {"project_id": "00000000-0000-0000-0000-000000000001"},
            "transition": {"from_phase": "review", "to_phase": "approved"},
            "guards": {"approval_quorum_met": False},
        },
    )

    assert result.passed is True
    assert repository.calls == [("00000000-0000-0000-0000-000000000001", "review")]


def test_approval_quorum_guard_blocks_when_ledger_rows_do_not_meet_review_quorum() -> None:
    evaluator, repository = make_evaluator(
        [
            ApprovalEntry(
                actor_email="partner@example.com",
                role="partner",
                decision="approved",
            )
        ]
    )

    result = evaluator.evaluate(
        "approval_quorum_met",
        {
            "project": {"project_id": "00000000-0000-0000-0000-000000000002"},
            "transition": {"from_phase": "review", "to_phase": "approved"},
            "guards": {"approval_quorum_met": True},
        },
    )

    assert result.passed is False
    assert "missing_roles" in str(result.reason)
    assert repository.calls == [("00000000-0000-0000-0000-000000000002", "review")]


def test_approval_quorum_guard_reuses_review_quorum_for_export_transition() -> None:
    evaluator, repository = make_evaluator(
        [
            ApprovalEntry(
                actor_email="partner@example.com",
                role="partner",
                decision="approved",
            ),
            ApprovalEntry(
                actor_email="ic@example.com",
                role="ic_member",
                decision="approved",
            ),
        ]
    )

    result = evaluator.evaluate(
        "approval_quorum_met",
        {
            "project": {"project_id": "00000000-0000-0000-0000-000000000003"},
            "transition": {"from_phase": "approved", "to_phase": "exported"},
            "guards": {},
        },
    )

    assert result.passed is True
    assert repository.calls == [("00000000-0000-0000-0000-000000000003", "review")]
