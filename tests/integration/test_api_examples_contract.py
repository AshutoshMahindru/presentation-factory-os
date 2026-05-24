from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

import api.workflow as workflow
from api.workflow import app


client = TestClient(app)

API_MEDIA_TYPE = "application/vnd.pfos.v3.2.4+json"
HEADERS = {
    "accept": API_MEDIA_TYPE,
    "content-type": API_MEDIA_TYPE,
}


class FakeProjectRepository:
    def __init__(self) -> None:
        self.projects: dict[str, SimpleNamespace] = {}
        self.approvals: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.transitions: list[dict[str, Any]] = []

    def create_project(
        self,
        name: str,
        audience: str,
        audience_profile: dict[str, Any],
        client_name: str | None = None,
        decision_required: str | None = None,
        objection_preemption_map: dict[str, Any] | None = None,
    ) -> SimpleNamespace:
        project_id = str(uuid4())
        project = SimpleNamespace(
            project_id=project_id,
            name=name,
            audience=audience,
            audience_profile=audience_profile,
            current_phase="created",
        )
        self.projects[project_id] = project
        return project

    def get_project(self, project_id: str) -> SimpleNamespace | None:
        return self.projects.get(project_id)

    def record_phase_transition(
        self,
        project_id: str,
        from_phase: str,
        to_phase: str,
        transition_kind: str,
        guard_results: list[dict[str, Any]],
        hard_gate_results: dict[str, Any],
        state_machine_version: str,
        reason: str | None,
        actor_email: str,
    ) -> None:
        self.transitions.append(
            {
                "project_id": project_id,
                "from_phase": from_phase,
                "to_phase": to_phase,
                "transition_kind": transition_kind,
                "guard_results": guard_results,
                "hard_gate_results": hard_gate_results,
                "state_machine_version": state_machine_version,
                "reason": reason,
                "actor_email": actor_email,
            }
        )

    def update_phase(self, project_id: str, to_phase: str) -> None:
        self.projects[project_id].current_phase = to_phase

    def record_approval(
        self,
        project_id: str,
        phase: str,
        actor_email: str,
        role: str,
        decision: str,
        rubric_score_snapshot: dict[str, Any],
        notes: str | None = None,
    ) -> None:
        self.approvals.setdefault((project_id, phase), []).append(
            {
                "actor_email": actor_email,
                "role": role,
                "decision": decision,
                "rubric_score_snapshot": rubric_score_snapshot,
                "notes": notes,
            }
        )

    def list_approvals_for_phase(self, project_id: str, phase: str) -> list[dict[str, Any]]:
        return list(self.approvals.get((project_id, phase), []))


class FakeOutboxRepository:
    def get_project_outbox_status(self, project_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            project_id=project_id,
            blocked=False,
            unprocessed_count=0,
            failed_count=0,
            oldest_unprocessed_age_seconds=None,
        )


class FakeStateMachine:
    version = "3.2.4"

    def validate_transition_with_guards(
        self,
        from_phase: str,
        to_phase: str,
        kind: str,
        context: dict[str, Any],
        reason: str | None,
    ) -> tuple[SimpleNamespace, tuple[SimpleNamespace, ...]]:
        guards = ()
        if from_phase == "intake" and to_phase == "strategy":
            guards = (
                SimpleNamespace(name="rubric_above_3_5", passed=True, reason=None),
                SimpleNamespace(name="thesis_audience_aligned", passed=True, reason=None),
                SimpleNamespace(name="audience_psychology_adequate", passed=True, reason=None),
                SimpleNamespace(name="no_blocking_rules", passed=True, reason=None),
            )

        return (
            SimpleNamespace(from_phase=from_phase, to_phase=to_phase, kind=kind),
            guards,
        )


@pytest.fixture
def fake_project_repository(monkeypatch) -> FakeProjectRepository:
    repository = FakeProjectRepository()
    monkeypatch.setattr(workflow, "project_repository", repository)
    monkeypatch.setattr(workflow, "outbox_repository", FakeOutboxRepository())
    return repository


def api_example_audience_profile() -> dict[str, object]:
    return {
        "decision_maker_type": "ic_partner",
        "risk_tolerance": "medium",
        "familiarity_with_topic": "informed",
        "known_objections": ["team_risk", "market_size", "timing"],
        "stakeholder_map": [
            {
                "role": "economic_buyer",
                "concern": "return on invested capital",
            },
            {
                "role": "technical_evaluator",
                "concern": "operational scalability",
            },
        ],
    }


def api_example_create_project_payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "audience": "Risk-aware investment committee evaluating a capital allocation decision",
        "audience_profile": api_example_audience_profile(),
        "objection_preemption_map": {
            "team_risk": {
                "planned_response": "Show advisor/operator coverage and phased execution gates",
                "target_phase": "narrative",
            },
            "market_size": {
                "planned_response": "Triangulate TAM/SAM/SOM with sourced demand proxies",
                "target_phase": "research",
            },
        },
    }


def create_project_from_api_examples(name: str) -> str:
    response = client.post(
        "/projects",
        headers=HEADERS,
        json=api_example_create_project_payload(name),
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["phase"] == "created"
    assert body["audience_profile_valid"] is True
    assert isinstance(body["project_id"], str)
    return str(body["project_id"])


def test_api_examples_create_project_contract(fake_project_repository: FakeProjectRepository) -> None:
    project_id = create_project_from_api_examples("Step 67 API Examples Create")

    assert project_id


def test_api_examples_phase_transition_contract(
    fake_project_repository: FakeProjectRepository,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workflow.StateMachine,
        "from_yaml",
        staticmethod(lambda: FakeStateMachine()),
    )

    project_id = create_project_from_api_examples("Step 67 API Examples Transition")

    created_to_intake = client.post(
        f"/projects/{project_id}/phase-transitions",
        headers=HEADERS,
        json={
            "from_phase": "created",
            "to_phase": "intake",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Start intake.",
            "guard_context": {"guards": {}},
        },
    )
    assert created_to_intake.status_code == 200, created_to_intake.json()

    response = client.post(
        f"/projects/{project_id}/phase-transitions",
        headers=HEADERS,
        json={
            "from_phase": "intake",
            "to_phase": "strategy",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Brief, audience profile, and decision definition are complete.",
            "guard_context": {
                "guards": {
                    "rubric_above_3_5": True,
                    "thesis_audience_aligned": True,
                },
                "rubric_score_id": "3ebec5e5-ec8e-45c0-ae80-ff4b02bfaa87",
                "approval_snapshot_id": "b4ea8e85-b2cc-47e7-9860-f5b85e64ea71",
            },
        },
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["project_id"] == project_id
    assert body["from_phase"] == "intake"
    assert body["to_phase"] == "strategy"
    assert body["status"] == "applied"
    assert {guard["name"] for guard in body["guards"]} == {
        "rubric_above_3_5",
        "thesis_audience_aligned",
        "audience_psychology_adequate",
        "no_blocking_rules",
    }
    assert all(guard["status"] == "pass" for guard in body["guards"])
    assert fake_project_repository.projects[project_id].current_phase == "strategy"


def test_api_examples_approval_submission_and_status_contract(
    fake_project_repository: FakeProjectRepository,
) -> None:
    project_id = create_project_from_api_examples("Step 67 API Examples Approval")

    ic_member = client.post(
        f"/projects/{project_id}/approvals",
        headers=HEADERS,
        json={
            "phase": "review",
            "actor_email": "ic.member@example.com",
            "role": "ic_member",
            "decision": "approved",
            "rubric_score_snapshot": {
                "overall_score": 4.25,
                "source_traceability": 4.5,
                "financial_validation": 4.2,
                "visual_qa": 4.1,
                "deck_completeness": 4.2,
            },
            "notes": "Approved for IC circulation. Confirm final source appendix remains attached at export.",
        },
    )

    assert ic_member.status_code == 200, ic_member.json()
    body = ic_member.json()
    assert body["project_id"] == project_id
    assert body["phase"] == "review"
    assert body["approval_recorded"] is True
    assert body["quorum_met"] is False
    assert body["approved_count"] == 1
    assert body["missing_roles"] == {}
    assert body["blocking_rejection"] is False

    partner = client.post(
        f"/projects/{project_id}/approvals",
        headers=HEADERS,
        json={
            "phase": "review",
            "actor_email": "partner@example.com",
            "role": "partner",
            "decision": "approved",
            "rubric_score_snapshot": {
                "overall_score": 4.4,
                "source_traceability": 4.3,
                "financial_validation": 4.4,
                "visual_qa": 4.2,
                "deck_completeness": 4.5,
            },
            "notes": "Partner approval for review exit.",
        },
    )
    assert partner.status_code == 200, partner.json()

    status = client.get(
        f"/projects/{project_id}/approvals/status/review",
        headers={"accept": API_MEDIA_TYPE},
    )

    assert status.status_code == 200, status.json()
    status_body = status.json()
    assert status_body == {
        "project_id": project_id,
        "phase": "review",
        "quorum_met": True,
        "decision_rule": "unanimous",
        "required_count": 2,
        "approved_count": 2,
        "rejected_count": 0,
        "abstained_count": 0,
        "changes_requested_count": 0,
        "missing_roles": {},
        "blocking_rejection": False,
        "escalation_status": "none",
        "escalation_reason": None,
    }
