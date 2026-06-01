from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

import api.workflow as workflow
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


@dataclass(frozen=True)
class FakeOutboxStatus:
    project_id: str
    blocked: bool
    unprocessed_count: int
    failed_count: int
    oldest_unprocessed_age_seconds: int | None


class FakeOutboxRepository:
    def __init__(self, status: FakeOutboxStatus) -> None:
        self.status = status
        self.calls: list[str] = []

    def get_project_outbox_status(self, project_id: str) -> FakeOutboxStatus:
        self.calls.append(project_id)
        return self.status


def test_outbox_status_endpoint_reports_clean_project(monkeypatch) -> None:
    project = project_repository.create_project(
        name="Step 44 Clean Outbox Project",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    fake_repository = FakeOutboxRepository(
        FakeOutboxStatus(
            project_id=project.project_id,
            blocked=False,
            unprocessed_count=0,
            failed_count=0,
            oldest_unprocessed_age_seconds=None,
        )
    )

    monkeypatch.setattr(workflow, "outbox_repository", fake_repository)

    response = client.get(f"/health/projects/{project.project_id}/outbox")

    assert response.status_code == 200
    body = response.json()

    assert fake_repository.calls == [project.project_id]
    assert body == {
        "project_id": project.project_id,
        "blocked": False,
        "unprocessed_count": 0,
        "failed_count": 0,
        "oldest_unprocessed_age_seconds": None,
    }


def test_outbox_status_endpoint_reports_blocked_project(monkeypatch) -> None:
    project = project_repository.create_project(
        name="Step 44 Blocked Outbox Project",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    fake_repository = FakeOutboxRepository(
        FakeOutboxStatus(
            project_id=project.project_id,
            blocked=True,
            unprocessed_count=3,
            failed_count=1,
            oldest_unprocessed_age_seconds=64,
        )
    )

    monkeypatch.setattr(workflow, "outbox_repository", fake_repository)

    response = client.get(f"/health/projects/{project.project_id}/outbox")

    assert response.status_code == 200
    body = response.json()

    assert fake_repository.calls == [project.project_id]
    assert body["project_id"] == project.project_id
    assert body["blocked"] is True
    assert body["unprocessed_count"] == 3
    assert body["failed_count"] == 1
    assert body["oldest_unprocessed_age_seconds"] == 64


def test_outbox_status_endpoint_404_for_unknown_project() -> None:
    response = client.get(
        "/health/projects/00000000-0000-0000-0000-000000000000/outbox"
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "project_not_found"
