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
    def __init__(
        self,
        projects: dict[str, Any],
        evidence_coverage: dict[str, Any] | None = None,
        days_in_phase: int = 0,
        approvals: list[dict[str, Any]] | None = None,
    ) -> None:
        self.projects = projects
        self.evidence_coverage = evidence_coverage
        self.days_in_phase = days_in_phase
        self.approvals = approvals or []
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def get_project(self, project_id: str) -> Any | None:
        self.calls.append(("get_project", (project_id,)))
        return self.projects.get(project_id)

    def get_project_evidence_coverage(self, project_id: str, phase: str) -> dict[str, Any]:
        self.calls.append(("get_project_evidence_coverage", (project_id, phase)))
        return self.evidence_coverage or {
            "ratio": 1.0,
            "source": "fake_repository",
        }

    def get_project_days_in_current_phase(self, project_id: str) -> int:
        self.calls.append(("get_project_days_in_current_phase", (project_id,)))
        return self.days_in_phase

    def list_approvals_for_phase(self, project_id: str, phase: str) -> list[dict[str, Any]]:
        self.calls.append(("list_approvals_for_phase", (project_id, phase)))
        return list(self.approvals)


class MinimalProjectRepository:
    def __init__(self, projects: dict[str, Any]) -> None:
        self.projects = projects

    def get_project(self, project_id: str) -> Any | None:
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

    def get_project_retraction_cascade_status(
        self,
        project_id: str,
    ) -> FakeRetractionCascadeStatus:
        self.calls.append(project_id)
        return self.status


class FakeHardGateRepository:
    def __init__(self, result: HardGateBundleResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def evaluate_no_blocking_rules(self, project_id: str) -> HardGateBundleResult:
        self.calls.append(project_id)
        return self.result


def test_project_health_endpoint_composes_existing_status_payloads(monkeypatch) -> None:
    project_id = "project-health-aggregate-clean"
    project = SimpleNamespace(project_id=project_id, current_phase="review")
    project_repository = FakeProjectRepository(
        projects={project_id: project},
        evidence_coverage={
            "ratio": 0.75,
            "covered_count": 3,
            "total_count": 4,
            "source": "test_evidence_repository",
        },
        days_in_phase=4,
        approvals=[
            {"actor_email": "partner@example.com", "role": "partner", "decision": "approved"},
            {"actor_email": "ic@example.com", "role": "ic_member", "decision": "approved"},
        ],
    )
    outbox_repository = FakeOutboxRepository(
        FakeOutboxStatus(
            project_id=project_id,
            blocked=False,
            unprocessed_count=0,
            failed_count=0,
            oldest_unprocessed_age_seconds=None,
        )
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
                    metadata={"unprocessed_count": 0, "failed_count": 0},
                ),
            ),
        )
    )

    monkeypatch.setattr(workflow, "project_repository", project_repository)
    monkeypatch.setattr(workflow, "outbox_repository", outbox_repository)
    monkeypatch.setattr(workflow, "source_lifecycle_repository", source_lifecycle_repository)
    monkeypatch.setattr(workflow, "hard_gate_repository", hard_gate_repository)

    response = client.get(f"/health/projects/{project_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["current_phase"] == "review"
    assert body["status"] == "ready"
    assert body["blocked"] is False
    assert body["health_score"] == 0.85
    assert body["evidence_coverage_ratio"] == 0.75
    assert body["evidence_coverage"] == {
        "ratio": 0.75,
        "covered_count": 3,
        "total_count": 4,
        "source": "test_evidence_repository",
    }
    assert body["open_retractions"] == 0
    assert body["days_in_current_phase"] == 4
    assert body["approval_velocity"] == {
        "approvals_per_day": 0.5,
        "approval_count": 2,
        "days_in_phase": 4,
        "source": "approval_ledger",
    }
    assert body["blocking_gates_status"] == "clear"
    assert body["outbox"]["blocked"] is False
    assert body["source_retractions"]["blocked"] is False
    assert body["hard_gates"]["passed"] is True
    assert outbox_repository.calls == [project_id]
    assert source_lifecycle_repository.calls == [project_id]
    assert hard_gate_repository.calls == [project_id]


def test_project_health_endpoint_reports_blocked_status_with_deterministic_fallbacks(
    monkeypatch,
) -> None:
    project_id = "project-health-aggregate-blocked"
    project = SimpleNamespace(project_id=project_id, current_phase="strategy")
    monkeypatch.setattr(
        workflow,
        "project_repository",
        MinimalProjectRepository({project_id: project}),
    )
    monkeypatch.setattr(
        workflow,
        "outbox_repository",
        FakeOutboxRepository(
            FakeOutboxStatus(
                project_id=project_id,
                blocked=True,
                unprocessed_count=2,
                failed_count=1,
                oldest_unprocessed_age_seconds=60,
            )
        ),
    )
    monkeypatch.setattr(
        workflow,
        "source_lifecycle_repository",
        FakeSourceLifecycleRepository(
            FakeRetractionCascadeStatus(
                project_id=project_id,
                blocked=True,
                pending_count=2,
                processing_count=1,
                failed_count=1,
                oldest_open_age_seconds=120,
            )
        ),
    )
    monkeypatch.setattr(
        workflow,
        "hard_gate_repository",
        FakeHardGateRepository(
            HardGateBundleResult(
                name="no_blocking_rules",
                passed=False,
                checks=(
                    HardGateCheckResult(
                        name="no_failed_or_unprocessed_outbox_items",
                        passed=False,
                        reason="project_has_failed_or_unprocessed_outbox_rows",
                    ),
                ),
            )
        ),
    )

    response = client.get(f"/health/projects/{project_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["blocked"] is True
    assert body["health_score"] == 0.5
    assert body["evidence_coverage"]["source"] == "deterministic_fallback"
    assert body["days_in_current_phase"] == 0
    assert body["approval_velocity"]["source"] == "deterministic_fallback"
    assert body["open_retractions"] == 4
    assert body["blocking_gates_status"] == "blocked"
    assert body["outbox"]["failed_count"] == 1
    assert body["source_retractions"]["oldest_open_age_seconds"] == 120
    assert body["hard_gates"]["failed_checks"] == [
        {
            "name": "no_failed_or_unprocessed_outbox_items",
            "reason": "project_has_failed_or_unprocessed_outbox_rows",
            "metadata": {},
        }
    ]


def test_project_health_endpoint_404_for_unknown_project(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "project_repository", MinimalProjectRepository({}))

    response = client.get("/health/projects/missing-project")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "project_not_found"
