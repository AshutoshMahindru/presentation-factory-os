import os
import subprocess
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from api.workflow import app


COMPOSE = ["docker", "compose", "-f", "docker-compose.apps.yaml"]
client = TestClient(app)
pytestmark = pytest.mark.skipif(
    os.environ.get("PFOS_RUN_LIVE_TESTS") != "1",
    reason="Live Docker/Postgres/Neo4j smoke test; set PFOS_RUN_LIVE_TESTS=1",
)


def psql(sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "pfos",
            "-d",
            "pfos",
            "-v",
            "ON_ERROR_STOP=1",
            "-A",
            "-t",
            "-F",
            "|",
            "-c",
            sql,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


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


def create_api_project_in_intake():
    response = client.post(
        "/projects",
        json={
            "name": "Outbox Gate API Project",
            "audience": "Investment committee",
            "audience_profile": valid_audience_profile(),
        },
    )
    assert response.status_code == 200
    project_id = response.json()["project_id"]

    response = client.post(
        f"/projects/{project_id}/phase-transitions",
        json={
            "from_phase": "created",
            "to_phase": "intake",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Start intake.",
            "guard_context": {"guards": {}},
        },
    )
    assert response.status_code == 200
    return project_id


def insert_matching_project_and_outbox_row(project_id: str):
    sql = f"""
    INSERT INTO projects (id, name, audience, audience_profile, current_phase)
    VALUES (
      '{project_id}',
      'Outbox Gate DB Project',
      'Investment committee',
      '{{}}'::jsonb,
      'intake'
    )
    ON CONFLICT (id) DO NOTHING;

    INSERT INTO outbox (project_id, target_store, operation_type, payload)
    VALUES (
      '{project_id}',
      'neo4j',
      'phase_transition_side_effect',
      '{{"event":"blocked_transition"}}'::jsonb
    );
    """
    result = psql(sql)
    assert result.returncode == 0, result.stderr


def test_phase_transition_blocks_when_project_has_unprocessed_outbox_rows():
    project_id = create_api_project_in_intake()
    insert_matching_project_and_outbox_row(project_id)

    response = client.post(
        f"/projects/{project_id}/phase-transitions",
        json={
            "from_phase": "intake",
            "to_phase": "strategy",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Try advancing with dirty outbox.",
            "guard_context": {
                "guards": {
                    "rubric_above_3_5": True,
                    "thesis_audience_aligned": True,
                    "no_blocking_rules": True,
                }
            },
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "transition_blocked"
    assert detail["blocking_guards"][0]["name"] == "no_failed_or_unprocessed_outbox_items"


def test_phase_transition_passes_after_outbox_worker_drains_rows():
    project_id = create_api_project_in_intake()
    insert_matching_project_and_outbox_row(project_id)

    worker = subprocess.run(
        ["python", "-m", "jobs.outbox_worker"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert worker.returncode == 0, worker.stderr

    response = client.post(
        f"/projects/{project_id}/phase-transitions",
        json={
            "from_phase": "intake",
            "to_phase": "strategy",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Advance after outbox drained.",
            "guard_context": {
                "guards": {
                    "rubric_above_3_5": True,
                    "thesis_audience_aligned": True,
                    "no_blocking_rules": True,
                }
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["to_phase"] == "strategy"
