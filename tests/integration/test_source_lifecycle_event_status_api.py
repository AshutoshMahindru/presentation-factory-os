from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

import api.sources as sources
from api.workflow import app


client = TestClient(app)


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

    def update_processing_status(self, **kwargs: Any) -> FakeEvent:
        self.calls.append(kwargs)
        return FakeEvent(
            event_id=kwargs["event_id"],
            project_id="project-1",
            source_id="source-1",
            event_type="retracted",
            processing_status=kwargs["processing_status"],
        )


def test_source_lifecycle_event_status_api_updates_to_processing(monkeypatch) -> None:
    fake_repository = FakeSourceLifecycleEventRepository()
    monkeypatch.setattr(sources, "source_lifecycle_event_repository", fake_repository)

    response = client.patch(
        "/sources/events/event-1/status",
        json={
            "processing_status": "processing",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body == {
        "event_id": "event-1",
        "project_id": "project-1",
        "source_id": "source-1",
        "event_type": "retracted",
        "processing_status": "processing",
    }

    assert fake_repository.calls == [
        {
            "event_id": "event-1",
            "processing_status": "processing",
            "last_error": None,
        }
    ]


def test_source_lifecycle_event_status_api_updates_to_failed_with_error(monkeypatch) -> None:
    fake_repository = FakeSourceLifecycleEventRepository()
    monkeypatch.setattr(sources, "source_lifecycle_event_repository", fake_repository)

    response = client.patch(
        "/sources/events/event-1/status",
        json={
            "processing_status": "failed",
            "last_error": "neo4j unavailable",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["processing_status"] == "failed"
    assert fake_repository.calls == [
        {
            "event_id": "event-1",
            "processing_status": "failed",
            "last_error": "neo4j unavailable",
        }
    ]


def test_source_lifecycle_event_status_api_422_for_invalid_status(monkeypatch) -> None:
    class RejectingRepository:
        def update_processing_status(self, **kwargs: Any) -> FakeEvent:
            raise ValueError("Unsupported processing_status: not_real")

    monkeypatch.setattr(sources, "source_lifecycle_event_repository", RejectingRepository())

    response = client.patch(
        "/sources/events/event-1/status",
        json={
            "processing_status": "not_real",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_source_lifecycle_event_status"


def test_source_lifecycle_event_status_api_404_for_missing_event(monkeypatch) -> None:
    class MissingRepository:
        def update_processing_status(self, **kwargs: Any) -> FakeEvent:
            raise LookupError("Source lifecycle event not found: event-missing")

    monkeypatch.setattr(sources, "source_lifecycle_event_repository", MissingRepository())

    response = client.patch(
        "/sources/events/event-missing/status",
        json={
            "processing_status": "processed",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "source_lifecycle_event_not_found"
