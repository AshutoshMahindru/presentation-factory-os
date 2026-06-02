from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

import api.sources as sources
from api.workflow import app


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
class FakeEvent:
    event_id: str
    project_id: str
    source_id: str
    event_type: str
    processing_status: str


class FakeSourceLifecycleEventRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create_event(self, **kwargs: Any) -> FakeEvent:
        self.calls.append(kwargs)
        return FakeEvent(
            event_id="event-123",
            project_id=kwargs["project_id"],
            source_id=kwargs["source_id"],
            event_type=kwargs["event_type"],
            processing_status=kwargs["processing_status"],
        )


class FakeProjectRepository:
    def __init__(self, existing_project_ids: set[str] | None = None) -> None:
        self.existing_project_ids = existing_project_ids or set()

    def get_project(self, project_id: str) -> Any | None:
        if project_id not in self.existing_project_ids:
            return None
        return SimpleNamespace(project_id=project_id, current_phase="created")


def test_source_lifecycle_event_api_creates_pending_retraction_event(monkeypatch) -> None:
    project_id = str(uuid4())

    fake_repository = FakeSourceLifecycleEventRepository()
    monkeypatch.setattr(sources, "project_repository", FakeProjectRepository({project_id}))
    monkeypatch.setattr(sources, "source_lifecycle_event_repository", fake_repository)

    response = client.post(
        "/sources/events",
        json={
            "project_id": project_id,
            "source_id": "source-abc",
            "event_type": "retracted",
            "source_version": "v2",
            "classification": "public",
            "event_payload": {"reason": "withdrawn by publisher"},
            "hmac_validated": True,
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body == {
        "event_id": "event-123",
        "project_id": project_id,
        "source_id": "source-abc",
        "event_type": "retracted",
        "processing_status": "pending",
    }

    assert fake_repository.calls == [
        {
            "project_id": project_id,
            "source_id": "source-abc",
            "event_type": "retracted",
            "event_payload": {"reason": "withdrawn by publisher"},
            "source_version": "v2",
            "classification": "public",
            "hmac_validated": True,
            "processing_status": "pending",
        }
    ]


def test_source_lifecycle_event_api_404_for_unknown_project(monkeypatch) -> None:
    monkeypatch.setattr(sources, "project_repository", FakeProjectRepository())

    response = client.post(
        "/sources/events",
        json={
            "project_id": "00000000-0000-0000-0000-000000000000",
            "source_id": "source-abc",
            "event_type": "retracted",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "project_not_found"


def test_source_lifecycle_event_api_422_for_invalid_event_type(monkeypatch) -> None:
    project_id = str(uuid4())

    class RejectingRepository:
        def create_event(self, **kwargs: Any) -> FakeEvent:
            raise ValueError("Unsupported lifecycle event_type: not_real")

    monkeypatch.setattr(sources, "project_repository", FakeProjectRepository({project_id}))
    monkeypatch.setattr(sources, "source_lifecycle_event_repository", RejectingRepository())

    response = client.post(
        "/sources/events",
        json={
            "project_id": project_id,
            "source_id": "source-abc",
            "event_type": "not_real",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_source_lifecycle_event"
