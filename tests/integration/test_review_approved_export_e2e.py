from __future__ import annotations

import os
from typing import Any

from fastapi.testclient import TestClient


os.environ.setdefault("COMPOSE_PROJECT_NAME", "pfos-dev")

from api.workflow import app, project_repository  # noqa: E402


client = TestClient(app)

API_MEDIA_TYPE = "application/vnd.pfos.v3.2.4+json"
HEADERS = {
    "accept": API_MEDIA_TYPE,
    "content-type": API_MEDIA_TYPE,
}


VALID_AUDIENCE_PROFILE = {
    "decision_maker_type": "ic_partner",
    "risk_tolerance": "medium",
    "familiarity_with_topic": "informed",
    "known_objections": ["market_size", "team_risk", "timing"],
    "stakeholder_map": [
        {
            "role": "economic_buyer",
            "concern": "return on invested capital",
        }
    ],
}


def error_detail(response_json: dict[str, Any]) -> dict[str, Any]:
    detail = response_json.get("detail")
    assert isinstance(detail, dict), response_json
    return detail


def blocking_guard_names(response_json: dict[str, Any]) -> set[str]:
    detail = error_detail(response_json)
    return {
        str(guard["name"])
        for guard in detail["blocking_guards"]
    }


def create_project_in_review() -> str:
    create_response = client.post(
        "/projects",
        headers=HEADERS,
        json={
            "name": "Step 69 Review Approved Export E2E",
            "audience": "Investment committee",
            "audience_profile": VALID_AUDIENCE_PROFILE,
        },
    )

    assert create_response.status_code == 200, create_response.json()
    project_id = str(create_response.json()["project_id"])
    project_repository.update_phase(project_id, "review")
    return project_id


def submit_review_approval(project_id: str, actor_email: str, role: str) -> None:
    response = client.post(
        f"/projects/{project_id}/approvals",
        headers=HEADERS,
        json={
            "phase": "review",
            "actor_email": actor_email,
            "role": role,
            "decision": "approved",
            "rubric_score_snapshot": {"overall_score": 4.4},
            "notes": f"{role} approval for review exit.",
        },
    )

    assert response.status_code == 200, response.json()
    assert response.json()["approval_recorded"] is True


def request_transition(project_id: str, from_phase: str, to_phase: str, guards: dict[str, bool]):
    return client.post(
        f"/projects/{project_id}/phase-transitions",
        headers=HEADERS,
        json={
            "from_phase": from_phase,
            "to_phase": to_phase,
            "transition_kind": "forward",
            "requested_by": "partner@example.com",
            "reason": f"Advance from {from_phase} to {to_phase}.",
            "guard_context": {"guards": guards},
        },
    )


def test_review_to_approved_and_exported_gate_e2e() -> None:
    project_id = create_project_in_review()

    blocked_without_quorum = request_transition(
        project_id=project_id,
        from_phase="review",
        to_phase="approved",
        guards={
            "rubric_above_4_0": True,
            "all_material_claims_sourced": True,
            "visual_qa_passed": True,
        },
    )

    assert blocked_without_quorum.status_code == 422
    assert "approval_quorum_met" in blocking_guard_names(blocked_without_quorum.json())

    submit_review_approval(project_id, "partner@example.com", "partner")
    submit_review_approval(project_id, "ic.member@example.com", "ic_member")

    approved = request_transition(
        project_id=project_id,
        from_phase="review",
        to_phase="approved",
        guards={
            "rubric_above_4_0": True,
            "all_material_claims_sourced": True,
            "visual_qa_passed": True,
        },
    )

    assert approved.status_code == 200, approved.json()
    assert approved.json()["to_phase"] == "approved"

    blocked_without_export_guards = request_transition(
        project_id=project_id,
        from_phase="approved",
        to_phase="exported",
        guards={},
    )

    assert blocked_without_export_guards.status_code == 422
    assert {
        "export_integrity",
        "no_pii_exposure",
    }.issubset(blocking_guard_names(blocked_without_export_guards.json()))

    exported = request_transition(
        project_id=project_id,
        from_phase="approved",
        to_phase="exported",
        guards={
            "export_integrity": True,
            "no_pii_exposure": True,
        },
    )

    assert exported.status_code == 200, exported.json()
    assert exported.json()["from_phase"] == "approved"
    assert exported.json()["to_phase"] == "exported"
    assert exported.json()["status"] == "applied"

    project = project_repository.get_project(project_id)
    assert project is not None
    assert project.current_phase == "exported"
