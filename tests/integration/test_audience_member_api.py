from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

import api.workflow as workflow


client = TestClient(workflow.app)


class FakeProjectRepository:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []

    def create_project(
        self,
        name: str,
        audience: str,
        audience_profile: dict[str, Any],
        client_name: str | None = None,
        decision_required: str | None = None,
        objection_preemption_map: dict[str, Any] | None = None,
    ) -> SimpleNamespace:
        self.create_calls.append(
            {
                "name": name,
                "audience": audience,
                "audience_profile": audience_profile,
                "client_name": client_name,
                "decision_required": decision_required,
                "objection_preemption_map": objection_preemption_map,
            }
        )
        return SimpleNamespace(project_id="project-1", current_phase="created")


def valid_audience_profile() -> dict[str, Any]:
    return {
        "decision_maker_type": "ic_partner",
        "risk_tolerance": "medium",
        "familiarity_with_topic": "informed",
        "known_objections": ["market_size", "execution_risk"],
        "stakeholder_map": [
            {
                "role": "economic_buyer",
                "concern": "return on invested capital",
                "influence_level": "high",
            },
            {
                "role": "technical_evaluator",
                "concern": "implementation risk",
                "influence_level": "medium",
            },
        ],
    }


def test_create_project_accepts_valid_audience_member_contract(monkeypatch) -> None:
    repository = FakeProjectRepository()
    monkeypatch.setattr(workflow, "project_repository", repository)

    response = client.post(
        "/projects",
        json={
            "name": "Audience Member Contract",
            "audience": "Investment committee",
            "audience_profile": valid_audience_profile(),
            "client_name": "Atlas Robotics",
            "decision_required": "Approve Series B investment.",
            "objection_preemption_map": {},
        },
    )

    assert response.status_code == 200, response.json()
    assert response.json() == {
        "project_id": "project-1",
        "phase": "created",
        "audience_profile_valid": True,
    }
    assert repository.create_calls == [
        {
            "name": "Audience Member Contract",
            "audience": "Investment committee",
            "audience_profile": valid_audience_profile(),
            "client_name": "Atlas Robotics",
            "decision_required": "Approve Series B investment.",
            "objection_preemption_map": {},
        }
    ]
