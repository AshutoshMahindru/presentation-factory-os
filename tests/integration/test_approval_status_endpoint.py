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


def test_approval_status_endpoint_reports_missing_review_quorum() -> None:
    project = project_repository.create_project(
        name="Step 38 Approval Status Missing Quorum",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    response = client.get(f"/projects/{project.project_id}/approvals/status/review")

    assert response.status_code == 200
    body = response.json()

    assert body["project_id"] == project.project_id
    assert body["phase"] == "review"
    assert body["quorum_met"] is False
    assert body["decision_rule"] == "unanimous"
    assert body["required_count"] == 2
    assert body["approved_count"] == 0
    assert body["rejected_count"] == 0
    assert body["changes_requested_count"] == 0
    assert body["abstained_count"] == 0
    assert body["missing_roles"] == {"ic_member": 1}
    assert body["blocking_rejection"] is False


def test_approval_status_endpoint_reports_met_review_quorum() -> None:
    project = project_repository.create_project(
        name="Step 38 Approval Status Met Quorum",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="partner@example.com",
        role="partner",
        decision="approved",
        rubric_score_snapshot={"overall": 4.3},
        notes="Partner approval.",
    )

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="ic@example.com",
        role="ic_member",
        decision="approved",
        rubric_score_snapshot={"overall": 4.4},
        notes="IC approval.",
    )

    response = client.get(f"/projects/{project.project_id}/approvals/status/review")

    assert response.status_code == 200
    body = response.json()

    assert body["project_id"] == project.project_id
    assert body["phase"] == "review"
    assert body["quorum_met"] is True
    assert body["decision_rule"] == "unanimous"
    assert body["required_count"] == 2
    assert body["approved_count"] == 2
    assert body["rejected_count"] == 0
    assert body["changes_requested_count"] == 0
    assert body["abstained_count"] == 0
    assert body["missing_roles"] == {}
    assert body["blocking_rejection"] is False


def test_approval_status_endpoint_reports_blocking_rejection() -> None:
    project = project_repository.create_project(
        name="Step 38 Approval Status Rejection",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="partner@example.com",
        role="partner",
        decision="approved",
        rubric_score_snapshot={"overall": 4.1},
        notes="Partner approval.",
    )

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="ic@example.com",
        role="ic_member",
        decision="rejected",
        rubric_score_snapshot={"overall": 2.0},
        notes="IC rejection.",
    )

    response = client.get(f"/projects/{project.project_id}/approvals/status/review")

    assert response.status_code == 200
    body = response.json()

    assert body["quorum_met"] is False
    assert body["approved_count"] == 1
    assert body["rejected_count"] == 1
    assert body["blocking_rejection"] is True


def test_approval_status_endpoint_404_for_unknown_project() -> None:
    response = client.get(
        "/projects/00000000-0000-0000-0000-000000000000/approvals/status/review"
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "project_not_found"


def test_approval_status_endpoint_422_for_unknown_phase() -> None:
    project = project_repository.create_project(
        name="Step 38 Approval Status Unknown Phase",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    response = client.get(f"/projects/{project.project_id}/approvals/status/visual_design")

    assert response.status_code == 422
    body = response.json()["detail"]

    assert body["error"] == "approval_status_unavailable"
    assert body["project_id"] == project.project_id
    assert body["phase"] == "visual_design"
