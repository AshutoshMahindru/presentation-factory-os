from __future__ import annotations

from typing import Any

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


def error_detail(response_json: dict[str, Any]) -> dict[str, Any]:
    """
    FastAPI wraps HTTPException detail payloads under the top-level `detail` key.
    Keep this helper explicit so the test documents API response shape.
    """
    detail = response_json.get("detail")
    assert isinstance(detail, dict), response_json
    return detail


def test_review_to_approved_blocks_without_ledger_quorum_then_passes_after_approvals() -> None:
    project = project_repository.create_project(
        name="Step 34 Approval Quorum Integration",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    project_repository.update_phase(project.project_id, "review")

    blocked_response = client.post(
        f"/projects/{project.project_id}/phase-transitions",
        json={
            "from_phase": "review",
            "to_phase": "approved",
            "transition_kind": "forward",
            "requested_by": "partner@example.com",
            "reason": "Attempt approval without ledger quorum.",
            "guard_context": {
                "guards": {
                    "rubric_above_4_0": True,
                    "all_material_claims_sourced": True,
                    "visual_qa_passed": True,
                    "no_blocking_rules": True,
                }
            },
        },
    )

    assert blocked_response.status_code == 422
    blocked_body = error_detail(blocked_response.json())

    assert blocked_body["error"] == "transition_blocked"
    assert blocked_body["project_id"] == project.project_id
    assert blocked_body["from_phase"] == "review"
    assert blocked_body["to_phase"] == "approved"
    assert any(
        guard["name"] == "approval_quorum_met"
        for guard in blocked_body["blocking_guards"]
    )

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="partner@example.com",
        role="partner",
        decision="approved",
        rubric_score_snapshot={"overall": 4.3},
        notes="Partner approval for review phase.",
    )

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="ic@example.com",
        role="ic_member",
        decision="approved",
        rubric_score_snapshot={"overall": 4.4},
        notes="IC member approval for review phase.",
    )

    passed_response = client.post(
        f"/projects/{project.project_id}/phase-transitions",
        json={
            "from_phase": "review",
            "to_phase": "approved",
            "transition_kind": "forward",
            "requested_by": "partner@example.com",
            "reason": "Ledger quorum now satisfied.",
            "guard_context": {
                "guards": {
                    "rubric_above_4_0": True,
                    "all_material_claims_sourced": True,
                    "visual_qa_passed": True,
                    "no_blocking_rules": True,
                }
            },
        },
    )

    assert passed_response.status_code == 200, passed_response.json()
    passed_body = passed_response.json()

    assert passed_body["project_id"] == project.project_id
    assert passed_body["from_phase"] == "review"
    assert passed_body["to_phase"] == "approved"
    assert passed_body["status"] == "applied"

    updated_project = project_repository.get_project(project.project_id)
    assert updated_project is not None
    assert updated_project.current_phase == "approved"
