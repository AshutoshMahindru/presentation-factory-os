from __future__ import annotations

import os

from fastapi.testclient import TestClient


os.environ.setdefault("COMPOSE_PROJECT_NAME", "pfos-dev")

from api.workflow import app  # noqa: E402


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
        },
        {
            "role": "technical_evaluator",
            "concern": "operational scalability",
        },
    ],
}


def test_project_lifecycle_created_to_intake_to_strategy_happy_path() -> None:
    create_response = client.post(
        "/projects",
        headers=HEADERS,
        json={
            "name": "Step 68 Project Lifecycle Happy Path",
            "audience": "Risk-aware investment committee evaluating a capital allocation decision",
            "audience_profile": VALID_AUDIENCE_PROFILE,
            "objection_preemption_map": {
                "market_size": {
                    "planned_response": "Triangulate TAM/SAM/SOM with sourced demand proxies",
                    "target_phase": "research",
                }
            },
        },
    )

    assert create_response.status_code == 200, create_response.json()
    create_body = create_response.json()
    project_id = create_body["project_id"]
    assert create_body["phase"] == "created"
    assert create_body["audience_profile_valid"] is True

    intake_response = client.post(
        f"/projects/{project_id}/phase-transitions",
        headers=HEADERS,
        json={
            "from_phase": "created",
            "to_phase": "intake",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Start intake after project creation.",
            "guard_context": {"guards": {}},
        },
    )

    assert intake_response.status_code == 200, intake_response.json()
    intake_body = intake_response.json()
    assert intake_body["project_id"] == project_id
    assert intake_body["from_phase"] == "created"
    assert intake_body["to_phase"] == "intake"
    assert intake_body["status"] == "applied"
    assert intake_body["guards"] == []

    strategy_response = client.post(
        f"/projects/{project_id}/phase-transitions",
        headers=HEADERS,
        json={
            "from_phase": "intake",
            "to_phase": "strategy",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Brief, audience profile, and decision definition are complete.",
            "guard_context": {
                "guards": {
                    "rubric_above_3_5": True,
                    "thesis_audience_aligned": True,
                }
            },
        },
    )

    assert strategy_response.status_code == 200, strategy_response.json()
    strategy_body = strategy_response.json()
    assert strategy_body["project_id"] == project_id
    assert strategy_body["from_phase"] == "intake"
    assert strategy_body["to_phase"] == "strategy"
    assert strategy_body["status"] == "applied"
    assert {guard["name"] for guard in strategy_body["guards"]} == {
        "rubric_above_3_5",
        "thesis_audience_aligned",
        "audience_psychology_adequate",
        "no_blocking_rules",
    }
    assert all(guard["status"] == "pass" for guard in strategy_body["guards"])
