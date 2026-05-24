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


def test_approval_status_ignores_approvals_before_latest_phase_entry() -> None:
    project = project_repository.create_project(
        name="Step 39 Approval Snapshot Window",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    project_repository.update_phase(project.project_id, "review")

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="old-partner@example.com",
        role="partner",
        decision="approved",
        rubric_score_snapshot={"overall": 4.3},
        notes="Old partner approval before latest review entry.",
    )

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="old-ic@example.com",
        role="ic_member",
        decision="approved",
        rubric_score_snapshot={"overall": 4.4},
        notes="Old IC approval before latest review entry.",
    )

    before_reentry = client.get(f"/projects/{project.project_id}/approvals/status/review")
    assert before_reentry.status_code == 200
    assert before_reentry.json()["quorum_met"] is True

    project_repository.record_phase_transition(
        project_id=project.project_id,
        from_phase="visual_design",
        to_phase="review",
        transition_kind="forward",
        guard_results=[],
        hard_gate_results={},
        state_machine_version="3.2.4",
        reason="Re-enter review after upstream revision.",
        actor_email="partner@example.com",
    )

    after_reentry = client.get(f"/projects/{project.project_id}/approvals/status/review")
    assert after_reentry.status_code == 200
    after_reentry_body = after_reentry.json()

    assert after_reentry_body["quorum_met"] is False
    assert after_reentry_body["approved_count"] == 0
    assert after_reentry_body["missing_roles"] == {"ic_member": 1}

    blocked_response = client.post(
        f"/projects/{project.project_id}/phase-transitions",
        json={
            "from_phase": "review",
            "to_phase": "approved",
            "transition_kind": "forward",
            "requested_by": "partner@example.com",
            "reason": "Old approvals must not satisfy quorum after re-entry.",
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
    assert any(
        guard["name"] == "approval_quorum_met"
        for guard in blocked_response.json()["detail"]["blocking_guards"]
    )

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="fresh-partner@example.com",
        role="partner",
        decision="approved",
        rubric_score_snapshot={"overall": 4.5},
        notes="Fresh partner approval after latest review entry.",
    )

    project_repository.record_approval(
        project_id=project.project_id,
        phase="review",
        actor_email="fresh-ic@example.com",
        role="ic_member",
        decision="approved",
        rubric_score_snapshot={"overall": 4.6},
        notes="Fresh IC approval after latest review entry.",
    )

    fresh_status = client.get(f"/projects/{project.project_id}/approvals/status/review")
    assert fresh_status.status_code == 200
    fresh_status_body = fresh_status.json()

    assert fresh_status_body["quorum_met"] is True
    assert fresh_status_body["approved_count"] == 2
    assert fresh_status_body["missing_roles"] == {}

    passed_response = client.post(
        f"/projects/{project.project_id}/phase-transitions",
        json={
            "from_phase": "review",
            "to_phase": "approved",
            "transition_kind": "forward",
            "requested_by": "partner@example.com",
            "reason": "Fresh approval snapshot satisfies quorum.",
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
    assert passed_response.json()["status"] == "applied"
