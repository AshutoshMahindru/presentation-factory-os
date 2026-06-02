from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.workflow as workflow
from api.workflow import app
from system.hard_gate_repository import HardGateBundleResult, HardGateCheckResult


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


class FakeHardGateRepository:
    def __init__(self, result: HardGateBundleResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def evaluate_no_blocking_rules(self, project_id: str) -> HardGateBundleResult:
        self.calls.append(project_id)
        return self.result


class FakeProjectRepository:
    def __init__(self, projects: dict[str, object]) -> None:
        self.projects = projects

    def get_project(self, project_id: str) -> object | None:
        return self.projects.get(project_id)


def test_hard_gate_status_endpoint_reports_pass(monkeypatch) -> None:
    project = SimpleNamespace(project_id="hard-gate-pass-project")

    fake_repository = FakeHardGateRepository(
        HardGateBundleResult(
            name="no_blocking_rules",
            passed=True,
            checks=(
                HardGateCheckResult("no_failed_or_unprocessed_outbox_items", True),
                HardGateCheckResult("no_stale_downstream_artifacts", True),
            ),
        )
    )
    monkeypatch.setattr(
        workflow,
        "project_repository",
        FakeProjectRepository({project.project_id: project}),
    )
    monkeypatch.setattr(workflow, "hard_gate_repository", fake_repository)

    response = client.get(f"/health/projects/{project.project_id}/hard-gates")

    assert response.status_code == 200
    body = response.json()

    assert fake_repository.calls == [project.project_id]
    assert body["project_id"] == project.project_id
    assert body["name"] == "no_blocking_rules"
    assert body["passed"] is True
    assert body["failed_checks"] == []


def test_hard_gate_status_endpoint_reports_failure(monkeypatch) -> None:
    project = SimpleNamespace(project_id="hard-gate-failure-project")

    fake_repository = FakeHardGateRepository(
        HardGateBundleResult(
            name="no_blocking_rules",
            passed=False,
            checks=(
                HardGateCheckResult(
                    name="no_blocking_rules_table_flags",
                    passed=False,
                    reason="project_has_open_blocking_rule_flags",
                    metadata={"blocking_count": 2},
                ),
            ),
        )
    )
    monkeypatch.setattr(
        workflow,
        "project_repository",
        FakeProjectRepository({project.project_id: project}),
    )
    monkeypatch.setattr(workflow, "hard_gate_repository", fake_repository)

    response = client.get(f"/health/projects/{project.project_id}/hard-gates")

    assert response.status_code == 200
    body = response.json()

    assert body["passed"] is False
    assert body["failed_checks"] == [
        {
            "name": "no_blocking_rules_table_flags",
            "reason": "project_has_open_blocking_rule_flags",
            "metadata": {"blocking_count": 2},
        }
    ]


def test_hard_gate_status_endpoint_404_for_unknown_project(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "project_repository", FakeProjectRepository({}))

    response = client.get("/health/projects/00000000-0000-0000-0000-000000000000/hard-gates")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "project_not_found"
