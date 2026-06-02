from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import api.workflow as workflow
from api.workflow import app


client = TestClient(app)


class FakeProjectRepository:
    def __init__(self) -> None:
        self.projects: dict[str, SimpleNamespace] = {}
        self.traces: dict[str, list[dict]] = {}
        self.routing_logs: dict[str, list[dict]] = {}
        self.rubric_scores: dict[tuple[str, str], list[dict]] = {}

    def create_project(
        self,
        name: str,
        audience: str,
        audience_profile: dict,
        client_name: str | None = None,
        decision_required: str | None = None,
        objection_preemption_map: dict | None = None,
    ) -> SimpleNamespace:
        project_id = f"project-{len(self.projects) + 1}"
        project = SimpleNamespace(
            project_id=project_id,
            name=name,
            audience=audience,
            audience_profile=audience_profile,
            current_phase="created",
        )
        self.projects[project_id] = project
        return project

    def get_project(self, project_id: str):
        return self.projects.get(project_id)

    def get_observability_metrics_snapshot(self) -> dict:
        return {
            "project_count": len(self.projects),
            "phase_transition_count": 1,
            "approval_count": 2,
            "open_outbox_count": 3,
            "failed_outbox_count": 4,
            "open_source_retraction_count": 5,
            "retrieval_routing_log_count": sum(
                len(logs) for logs in self.routing_logs.values()
            ),
            "rubric_score_count": sum(
                len(scores) for scores in self.rubric_scores.values()
            ),
        }

    def list_phase_traces(self, project_id: str) -> list[dict]:
        return self.traces.get(project_id, [])

    def list_retrieval_routing_logs(self, project_id: str) -> list[dict]:
        return self.routing_logs.get(project_id, [])

    def list_rubric_scores(self, project_id: str, phase: str) -> list[dict]:
        return self.rubric_scores.get((project_id, phase), [])


@pytest.fixture
def fake_project_repository(monkeypatch) -> FakeProjectRepository:
    repository = FakeProjectRepository()
    monkeypatch.setattr(workflow, "project_repository", repository)
    return repository


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


def create_project(name: str = "Observability Endpoint Project") -> str:
    response = client.post(
        "/projects",
        json={
            "name": name,
            "audience": "Investment committee",
            "audience_profile": valid_audience_profile(),
        },
    )
    assert response.status_code == 200
    return response.json()["project_id"]


def assert_uuid(value: str) -> None:
    UUID(value)


def seed_observability_rows(
    repository: FakeProjectRepository, project_id: str
) -> tuple[str, str]:
    trace_id = "11111111-1111-1111-1111-111111111111"
    request_id = "22222222-2222-2222-2222-222222222222"
    assert_uuid(trace_id)
    assert_uuid(request_id)
    repository.traces[project_id] = [
        {
            "trace_id": trace_id,
            "phase": "strategy",
            "span_name": "route-evidence",
            "service_name": "retrieval-engine",
            "started_at": "2026-01-01T00:00:00Z",
            "ended_at": "2026-01-01T00:00:02Z",
            "duration_ms": 2000,
            "status": "success",
            "metadata": {"mode": "hybrid"},
        }
    ]
    repository.routing_logs[project_id] = [
        {
            "request_id": request_id,
            "query": "market sizing evidence",
            "query_classification": "strategic",
            "mode": "hybrid",
            "forced_hybrid": True,
            "escalation_reason": "low_confidence",
            "confidence": 0.82,
            "item_count": 7,
            "gaps": [{"missing": "customer proof"}],
            "created_at": "2026-01-01T00:00:03Z",
        }
    ]
    repository.rubric_scores[(project_id, "strategy")] = [
        {
            "dimension": "audience_alignment",
            "score_version": 1,
            "score": 4.25,
            "weight": 0.4,
            "evaluator_type": "deterministic",
            "evaluator_model": None,
            "blocking": False,
            "threshold": 3.5,
            "trace_id": trace_id,
            "created_at": "2026-01-01T00:00:04Z",
        }
    ]
    return trace_id, request_id


def test_metrics_endpoint_returns_prometheus_snapshot(fake_project_repository):
    project_id = create_project("Observability Metrics Project")
    seed_observability_rows(fake_project_repository, project_id)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# TYPE pfos_projects_total counter" in response.text
    assert "pfos_open_outbox_items " in response.text
    assert "pfos_retrieval_routing_logs_total " in response.text


def test_traces_endpoint_returns_project_phase_traces(fake_project_repository):
    project_id = create_project("Observability Traces Project")
    trace_id, _ = seed_observability_rows(fake_project_repository, project_id)

    response = client.get(f"/traces/{project_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["traces"][0] == {
        "trace_id": trace_id,
        "phase": "strategy",
        "span_name": "route-evidence",
        "service_name": "retrieval-engine",
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:02Z",
        "duration_ms": 2000,
        "status": "success",
        "metadata": {"mode": "hybrid"},
    }


def test_retrieval_routing_endpoint_returns_project_logs(fake_project_repository):
    project_id = create_project("Observability Routing Project")
    _, request_id = seed_observability_rows(fake_project_repository, project_id)

    response = client.get(f"/observability/retrieval-routing/{project_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["routing_log_count"] == 1
    assert payload["routing_logs"][0] == {
        "request_id": request_id,
        "query": "market sizing evidence",
        "query_classification": "strategic",
        "mode": "hybrid",
        "forced_hybrid": True,
        "escalation_reason": "low_confidence",
        "confidence": 0.82,
        "item_count": 7,
        "gaps": [{"missing": "customer proof"}],
        "created_at": "2026-01-01T00:00:03Z",
    }


def test_rubric_endpoint_returns_phase_scores(fake_project_repository):
    project_id = create_project("Observability Rubric Project")
    trace_id, _ = seed_observability_rows(fake_project_repository, project_id)

    response = client.get(f"/observability/rubric/{project_id}/strategy")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["phase"] == "strategy"
    assert payload["score_count"] == 1
    assert payload["scores"][0] == {
        "dimension": "audience_alignment",
        "score_version": 1,
        "score": 4.25,
        "weight": 0.4,
        "evaluator_type": "deterministic",
        "evaluator_model": None,
        "blocking": False,
        "threshold": 3.5,
        "trace_id": trace_id,
        "created_at": "2026-01-01T00:00:04Z",
    }


def test_observability_endpoints_return_404_for_unknown_project(fake_project_repository):
    missing_project_id = "00000000-0000-0000-0000-000000000000"

    assert client.get(f"/traces/{missing_project_id}").status_code == 404
    assert client.get(f"/observability/retrieval-routing/{missing_project_id}").status_code == 404
    assert client.get(f"/observability/rubric/{missing_project_id}/strategy").status_code == 404
