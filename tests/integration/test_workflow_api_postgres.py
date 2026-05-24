from fastapi.testclient import TestClient

from api.workflow import app


client = TestClient(app)


def valid_audience_profile():
    return {
        "decision_maker_type": "ic_partner",
        "risk_tolerance": "medium",
        "familiarity_with_topic": "informed",
        "known_objections": ["pricing", "timing", "team_risk"],
        "stakeholder_map": [
            {
                "role": "economic_buyer",
                "concern": "roi",
            }
        ],
    }


def create_project():
    response = client.post(
        "/projects",
        json={
            "name": "Postgres Workflow Project",
            "audience": "Risk-aware investment committee",
            "audience_profile": valid_audience_profile(),
            "objection_preemption_map": {},
        },
    )
    assert response.status_code == 200
    return response.json()["project_id"]


def test_postgres_create_project():
    response = client.post(
        "/projects",
        json={
            "name": "Postgres Create Project",
            "audience": "Risk-aware investment committee",
            "audience_profile": valid_audience_profile(),
        },
    )

    assert response.status_code == 200
    assert response.json()["phase"] == "created"


def test_postgres_created_to_intake_transition():
    project_id = create_project()

    response = client.post(
        f"/projects/{project_id}/phase-transitions",
        json={
            "from_phase": "created",
            "to_phase": "intake",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Start intake.",
            "guard_context": {"guards": {}},
        },
    )

    assert response.status_code == 200
    assert response.json()["to_phase"] == "intake"


def test_postgres_intake_to_strategy_transition_with_guards():
    project_id = create_project()

    client.post(
        f"/projects/{project_id}/phase-transitions",
        json={
            "from_phase": "created",
            "to_phase": "intake",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Start intake.",
            "guard_context": {"guards": {}},
        },
    )

    response = client.post(
        f"/projects/{project_id}/phase-transitions",
        json={
            "from_phase": "intake",
            "to_phase": "strategy",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Brief and audience ready.",
            "guard_context": {
                "guards": {
                    "rubric_above_3_5": True,
                    "thesis_audience_aligned": True,
                    "no_blocking_rules": True,
                }
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["to_phase"] == "strategy"
