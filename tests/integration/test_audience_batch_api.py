from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.workflow as workflow


client = TestClient(workflow.app)


class RejectingProjectRepository:
    def create_project(self, **kwargs: Any) -> None:
        raise AssertionError("invalid audience profiles must not be persisted")


def valid_audience_profile() -> dict[str, Any]:
    return {
        "decision_maker_type": "ic_partner",
        "risk_tolerance": "medium",
        "familiarity_with_topic": "informed",
        "known_objections": ["pricing", "timing"],
        "stakeholder_map": [
            {
                "role": "economic_buyer",
                "concern": "roi",
            }
        ],
    }


def create_project_payload(audience_profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "Audience Batch Contract",
        "audience": "Investment committee",
        "audience_profile": audience_profile,
        "objection_preemption_map": {},
    }


@pytest.mark.parametrize(
    ("audience_profile", "expected_message"),
    [
        (
            {
                key: value
                for key, value in valid_audience_profile().items()
                if key != "decision_maker_type"
            },
            "decision_maker_type",
        ),
        (
            {**valid_audience_profile(), "risk_tolerance": "reckless"},
            "risk_tolerance",
        ),
        (
            {**valid_audience_profile(), "known_objections": ["unsupported"]},
            "known_objections",
        ),
        (
            {**valid_audience_profile(), "stakeholder_map": []},
            "stakeholder_map",
        ),
        (
            {
                **valid_audience_profile(),
                "stakeholder_map": [
                    {
                        "role": "economic_buyer",
                        "concern": "roi",
                        "unexpected": "not allowed",
                    }
                ],
            },
            "unexpected",
        ),
        (
            {**valid_audience_profile(), "unexpected": "not allowed"},
            "unexpected",
        ),
    ],
)
def test_create_project_rejects_invalid_audience_profiles_in_batch(
    audience_profile: dict[str, Any],
    expected_message: str,
    monkeypatch,
) -> None:
    monkeypatch.setattr(workflow, "project_repository", RejectingProjectRepository())

    response = client.post(
        "/projects",
        json=create_project_payload(audience_profile),
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "validation_failed"
    assert detail["blocking_gate"] == "audience_psychology_adequate"
    assert expected_message in detail["message"]
