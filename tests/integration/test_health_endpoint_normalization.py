from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

import api.workflow as workflow
from api.workflow import app
from system.hard_gate_repository import HardGateBundleResult, HardGateCheckResult


client = TestClient(app)


@dataclass(frozen=True)
class FakeOutboxStatus:
    project_id: str
    blocked: bool
    unprocessed_count: int
    failed_count: int
    oldest_unprocessed_age_seconds: int | None


@dataclass(frozen=True)
class FakeRetractionCascadeStatus:
    project_id: str
    blocked: bool
    pending_count: int
    processing_count: int
    failed_count: int
    oldest_open_age_seconds: int | None


class FakeProjectRepository:
    def __init__(self, projects: dict[str, Any]) -> None:
        self.projects = projects
        self.calls: list[str] = []

    def get_project(self, project_id: str) -> Any | None:
        self.calls.append(project_id)
        return self.projects.get(project_id)


class FakeOutboxRepository:
    def __init__(self, status: FakeOutboxStatus) -> None:
        self.status = status
        self.calls: list[str] = []

    def get_project_outbox_status(self, project_id: str) -> FakeOutboxStatus:
        self.calls.append(project_id)
        return self.status


class FakeSourceLifecycleRepository:
    def __init__(self, status: FakeRetractionCascadeStatus) -> None:
        self.status = status
        self.calls: list[str] = []

    def get_project_retraction_cascade_status(self, project_id: str) -> FakeRetractionCascadeStatus:
        self.calls.append(project_id)
        return self.status


class FakeHardGateRepository:
    def __init__(self, result: HardGateBundleResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def evaluate_no_blocking_rules(self, project_id: str) -> HardGateBundleResult:
        self.calls.append(project_id)
        return self.result


def test_service_health_and_readiness_are_normalized() -> None:
    assert client.get("/health").json() == {
        "service": "workflow-service",
        "status": "ok",
    }

    assert client.get("/ready").json() == {
        "service": "workflow-service",
        "status": "ready",
    }


def test_project_outbox_health_endpoint_uses_centralized_status(monkeypatch) -> None:
    project_id = "project-health-normalization"
    project_repository = FakeProjectRepository(
        {project_id: SimpleNamespace(project_id=project_id)}
    )
    outbox_repository = FakeOutboxRepository(
        FakeOutboxStatus(
            project_id=project_id,
            blocked=True,
            unprocessed_count=2,
            failed_count=1,
            oldest_unprocessed_age_seconds=55,
        )
    )

    monkeypatch.setattr(workflow, "project_repository", project_repository)
    monkeypatch.setattr(workflow, "outbox_repository", outbox_repository)

    response = client.get(f"/health/projects/{project_id}/outbox")

    assert response.status_code == 200
    assert project_repository.calls == [project_id]
    assert outbox_repository.calls == [project_id]
    assert response.json() == {
        "project_id": project_id,
        "blocked": True,
        "unprocessed_count": 2,
        "failed_count": 1,
        "oldest_unprocessed_age_seconds": 55,
    }


def test_project_health_subresources_share_unknown_project_404(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "project_repository", FakeProjectRepository({}))

    for path in (
        "/health/projects/missing-project/outbox",
        "/health/projects/missing-project/source-retractions",
        "/health/projects/missing-project/hard-gates",
    ):
        response = client.get(path)

        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "project_not_found"


def test_project_health_subresources_return_read_only_status(monkeypatch) -> None:
    project_id = "project-health-read-only"
    project_repository = FakeProjectRepository(
        {project_id: SimpleNamespace(project_id=project_id)}
    )
    source_lifecycle_repository = FakeSourceLifecycleRepository(
        FakeRetractionCascadeStatus(
            project_id=project_id,
            blocked=False,
            pending_count=0,
            processing_count=0,
            failed_count=0,
            oldest_open_age_seconds=None,
        )
    )
    hard_gate_repository = FakeHardGateRepository(
        HardGateBundleResult(
            name="no_blocking_rules",
            passed=True,
            checks=(
                HardGateCheckResult(
                    name="no_failed_or_unprocessed_outbox_items",
                    passed=True,
                    metadata={
                        "unprocessed_count": 0,
                        "failed_count": 0,
                        "oldest_unprocessed_age_seconds": None,
                    },
                ),
            ),
        )
    )

    monkeypatch.setattr(workflow, "project_repository", project_repository)
    monkeypatch.setattr(workflow, "source_lifecycle_repository", source_lifecycle_repository)
    monkeypatch.setattr(workflow, "hard_gate_repository", hard_gate_repository)

    retractions = client.get(f"/health/projects/{project_id}/source-retractions")
    hard_gates = client.get(f"/health/projects/{project_id}/hard-gates")

    assert retractions.status_code == 200
    assert retractions.json() == {
        "project_id": project_id,
        "blocked": False,
        "pending_count": 0,
        "processing_count": 0,
        "failed_count": 0,
        "oldest_open_age_seconds": None,
    }

    assert hard_gates.status_code == 200
    assert hard_gates.json()["project_id"] == project_id
    assert hard_gates.json()["passed"] is True
