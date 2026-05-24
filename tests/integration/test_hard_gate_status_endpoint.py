from __future__ import annotations

from fastapi.testclient import TestClient

import api.workflow as workflow
from api.workflow import app, project_repository
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


def test_hard_gate_status_endpoint_reports_pass(monkeypatch) -> None:
    project = project_repository.create_project(
        name="Step 50 Hard Gate Status Pass",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

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
    project = project_repository.create_project(
        name="Step 50 Hard Gate Status Failure",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

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


def test_hard_gate_status_endpoint_404_for_unknown_project() -> None:
    response = client.get("/health/projects/00000000-0000-0000-0000-000000000000/hard-gates")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "project_not_found"
