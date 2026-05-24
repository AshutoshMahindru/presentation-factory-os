from fastapi.testclient import TestClient

from api.workflow import PROJECTS, app


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
            "name": "Series A IC Deck",
            "audience": "Risk-aware investment committee",
            "audience_profile": valid_audience_profile(),
            "objection_preemption_map": {},
        },
    )
    assert response.status_code == 200
    return response.json()["project_id"]


def setup_function():
    PROJECTS.clear()


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_project_with_valid_audience_profile():
    response = client.post(
        "/projects",
        json={
            "name": "Series A IC Deck",
            "audience": "Risk-aware investment committee",
            "audience_profile": valid_audience_profile(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == "created"
    assert body["audience_profile_valid"] is True


def test_create_project_with_invalid_audience_profile_fails():
    profile = valid_audience_profile()
    profile["risk_tolerance"] = "reckless"

    response = client.post(
        "/projects",
        json={
            "name": "Series A IC Deck",
            "audience": "Risk-aware investment committee",
            "audience_profile": profile,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["blocking_gate"] == "audience_psychology_adequate"


def test_created_to_intake_transition_applies():
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
    assert response.json()["status"] == "applied"
    assert PROJECTS[project_id]["current_phase"] == "intake"


def test_intake_to_strategy_blocks_when_guard_missing():
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
            "reason": "Try strategy.",
            "guard_context": {
                "guards": {
                    "rubric_above_3_5": True,
                    "thesis_audience_aligned": True
                }
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "transition_blocked"


def test_intake_to_strategy_applies_when_guards_pass():
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
            "reason": "Brief and audience are ready.",
            "guard_context": {
                "guards": {
                    "rubric_above_3_5": True,
                    "thesis_audience_aligned": True,
                    "no_blocking_rules": True
                }
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["to_phase"] == "strategy"
    assert PROJECTS[project_id]["current_phase"] == "strategy"
