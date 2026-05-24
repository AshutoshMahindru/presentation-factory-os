from __future__ import annotations

from fastapi.testclient import TestClient

from api.workflow import app, project_repository


client = TestClient(app)


VALID_AUDIENCE_PROFILE = {
    "decision_maker_type": "ic_partner",
    "risk_tolerance": "medium",
    "familiarity_with_topic": "informed",
    "known_objections": ["market_size", "team_risk"],
    "stakeholder_map": [
        {
            "role": "economic_buyer",
            "concern": "return on invested capital",
        }
    ],
}


def test_approval_status_reports_no_escalation_without_blocking_rejection() -> None:
    project = project_repository.create_project(
        name="Step 41 No Escalation",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    response = client.get(f"/projects/{project.project_id}/approvals/status/review")

    assert response.status_code == 200
    body = response.json()

    assert body["quorum_met"] is False
    assert body["blocking_rejection"] is False
    assert body["escalation_status"] == "none"
    assert body["escalation_reason"] is None


def test_approval_status_reports_senior_partner_rejection_escalation() -> None:
    project = project_repository.create_project(
        name="Step 41 Senior Partner Escalation",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="senior@example.com",
        role="senior_partner",
        decision="rejected",
        rubric_score_snapshot={"overall": 2.0},
        notes="Senior partner rejection.",
    )

    response = client.get(f"/projects/{project.project_id}/approvals/status/review")

    assert response.status_code == 200
    body = response.json()

    assert body["quorum_met"] is False
    assert body["blocking_rejection"] is True
    assert body["rejected_count"] == 1
    assert body["escalation_status"] == "attention_required"
    assert body["escalation_reason"] == "rejection_by_senior_partner"


def test_approval_status_reports_changes_requested_escalation() -> None:
    project = project_repository.create_project(
        name="Step 41 Changes Requested Escalation",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="partner@example.com",
        role="partner",
        decision="changes_requested",
        rubric_score_snapshot={"overall": 3.1},
        notes="Needs revision.",
    )

    response = client.get(f"/projects/{project.project_id}/approvals/status/review")

    assert response.status_code == 200
    body = response.json()

    assert body["quorum_met"] is False
    assert body["blocking_rejection"] is True
    assert body["changes_requested_count"] == 1
    assert body["escalation_status"] == "attention_required"
    assert body["escalation_reason"] == "changes_requested"


def test_approval_status_reports_general_review_rejection_escalation() -> None:
    project = project_repository.create_project(
        name="Step 41 General Review Rejection",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="ic@example.com",
        role="ic_member",
        decision="rejected",
        rubric_score_snapshot={"overall": 2.2},
        notes="IC rejection.",
    )

    response = client.get(f"/projects/{project.project_id}/approvals/status/review")

    assert response.status_code == 200
    body = response.json()

    assert body["quorum_met"] is False
    assert body["blocking_rejection"] is True
    assert body["rejected_count"] == 1
    assert body["escalation_status"] == "attention_required"
    assert body["escalation_reason"] == "review_rejection"
