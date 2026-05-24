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
class FakeRetractionCascadeStatus:
    project_id: str
    blocked: bool
    pending_count: int
    processing_count: int
    failed_count: int
    oldest_open_age_seconds: int | None


class FakeSourceLifecycleRepository:
    def __init__(self, status: FakeRetractionCascadeStatus) -> None:
        self.status = status
        self.calls: list[str] = []

    def get_project_retraction_cascade_status(self, project_id: str) -> FakeRetractionCascadeStatus:
        self.calls.append(project_id)
        return self.status


def test_source_retraction_status_endpoint_reports_clean_project(monkeypatch) -> None:
    project = project_repository.create_project(
        name="Step 47 Clean Source Retraction Project",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    fake_repository = FakeSourceLifecycleRepository(
        FakeRetractionCascadeStatus(
            project_id=project.project_id,
            blocked=False,
            pending_count=0,
            processing_count=0,
            failed_count=0,
            oldest_open_age_seconds=None,
        )
    )

    monkeypatch.setattr(workflow, "source_lifecycle_repository", fake_repository)

    response = client.get(f"/health/projects/{project.project_id}/source-retractions")

    assert response.status_code == 200
    body = response.json()

    assert fake_repository.calls == [project.project_id]
    assert body == {
        "project_id": project.project_id,
        "blocked": False,
        "pending_count": 0,
        "processing_count": 0,
        "failed_count": 0,
        "oldest_open_age_seconds": None,
    }


def test_source_retraction_status_endpoint_reports_blocked_project(monkeypatch) -> None:
    project = project_repository.create_project(
        name="Step 47 Blocked Source Retraction Project",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    fake_repository = FakeSourceLifecycleRepository(
        FakeRetractionCascadeStatus(
            project_id=project.project_id,
            blocked=True,
            pending_count=2,
            processing_count=1,
            failed_count=1,
            oldest_open_age_seconds=77,
        )
    )

    monkeypatch.setattr(workflow, "source_lifecycle_repository", fake_repository)

    response = client.get(f"/health/projects/{project.project_id}/source-retractions")

    assert response.status_code == 200
    body = response.json()

    assert fake_repository.calls == [project.project_id]
    assert body["project_id"] == project.project_id
    assert body["blocked"] is True
    assert body["pending_count"] == 2
    assert body["processing_count"] == 1
    assert body["failed_count"] == 1
    assert body["oldest_open_age_seconds"] == 77


def test_source_retraction_status_endpoint_404_for_unknown_project() -> None:
    response = client.get(
        "/health/projects/00000000-0000-0000-0000-000000000000/source-retractions"
    )

    assert response.status_code == 404, response.json()
    body = response.json()
    assert isinstance(body, dict), body
    assert body["detail"]["error"] == "project_not_found"
