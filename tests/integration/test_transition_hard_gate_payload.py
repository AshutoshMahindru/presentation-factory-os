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
    def get_project_outbox_status(self, project_id: str) -> FakeOutboxStatus:
        return FakeOutboxStatus(
            project_id=project_id,
            blocked=True,
            unprocessed_count=4,
            failed_count=1,
            oldest_unprocessed_age_seconds=123,
        )


def test_transition_hard_gate_payload_is_normalized_for_outbox_block(monkeypatch) -> None:
    project = project_repository.create_project(
        name="Step 50 Transition Hard Gate Payload",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )
    project_repository.update_phase(project.project_id, "intake")

    monkeypatch.setattr(workflow, "outbox_repository", FakeOutboxRepository())

    response = client.post(
        f"/projects/{project.project_id}/phase-transitions",
        json={
            "from_phase": "intake",
            "to_phase": "strategy",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Should be blocked by outbox.",
            "guard_context": {
                "guards": {
                    "rubric_above_3_5": True,
                    "thesis_audience_aligned": True,
                }
            },
        },
    )

    assert response.status_code == 422
    body = response.json()["detail"]

    assert body["error"] == "transition_blocked"
    assert body["blocking_guards"] == [
        {
            "name": "no_failed_or_unprocessed_outbox_items",
            "reason": "project_has_failed_or_unprocessed_outbox_rows",
            "unprocessed_count": 4,
            "failed_count": 1,
            "oldest_unprocessed_age_seconds": 123,
        }
    ]
