import pytest

from system.approval_quorum import (
    APPROVED,
    REJECTED,
    ApprovalEntry,
    ApprovalQuorum,
    InvalidApprovalRoleError,
)


def test_intake_quorum_allows_single_analyst_approval():
    quorum = ApprovalQuorum.from_yaml()
    result = quorum.evaluate(
        "intake",
        [ApprovalEntry(actor_email="a@example.com", role="analyst", decision=APPROVED)],
    )
    assert result.quorum_met is True


def test_strategy_requires_partner_minimum_role():
    quorum = ApprovalQuorum.from_yaml()
    result = quorum.evaluate(
        "strategy",
        [ApprovalEntry(actor_email="s@example.com", role="senior_partner", decision=APPROVED)],
    )
    assert result.quorum_met is False
    assert result.missing_roles == {"partner": 1}


def test_financial_model_requires_two_approvals_and_one_partner():
    quorum = ApprovalQuorum.from_yaml()
    result = quorum.evaluate(
        "financial_model",
        [
            ApprovalEntry(actor_email="a@example.com", role="analyst", decision=APPROVED),
            ApprovalEntry(actor_email="p@example.com", role="partner", decision=APPROVED),
        ],
    )
    assert result.quorum_met is True


def test_review_unanimous_blocks_on_rejection():
    quorum = ApprovalQuorum.from_yaml()
    result = quorum.evaluate(
        "review",
        [
            ApprovalEntry(actor_email="p@example.com", role="partner", decision=APPROVED),
            ApprovalEntry(actor_email="ic@example.com", role="ic_member", decision=REJECTED),
        ],
    )
    assert result.quorum_met is False
    assert result.blocking_rejection is True


def test_invalid_role_for_phase_fails():
    quorum = ApprovalQuorum.from_yaml()
    with pytest.raises(InvalidApprovalRoleError):
        quorum.evaluate(
            "strategy",
            [ApprovalEntry(actor_email="a@example.com", role="analyst", decision=APPROVED)],
        )
