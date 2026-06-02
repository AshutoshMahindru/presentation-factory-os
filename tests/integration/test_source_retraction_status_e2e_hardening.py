from __future__ import annotations

import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("COMPOSE_PROJECT_NAME", "pfos-dev")

from api.workflow import app, project_repository  # noqa: E402
from jobs.outbox_worker import OutboxWorker  # noqa: E402
from system.outbox_repository import OutboxRepository  # noqa: E402
from system.source_lifecycle_event_repository import SourceLifecycleEventRepository  # noqa: E402


pytestmark = pytest.mark.skipif(
    os.environ.get("PFOS_RUN_LIVE_TESTS") != "1",
    reason="Live Docker/Postgres/Neo4j smoke test; set PFOS_RUN_LIVE_TESTS=1",
)

client = TestClient(app)

API_MEDIA_TYPE = "application/vnd.pfos.v3.2.4+json"
HEADERS = {
    "accept": API_MEDIA_TYPE,
    "content-type": API_MEDIA_TYPE,
}

VALID_AUDIENCE_PROFILE = {
    "decision_maker_type": "ic_partner",
    "risk_tolerance": "medium",
    "familiarity_with_topic": "informed",
    "known_objections": ["market_size", "team_risk", "timing"],
    "stakeholder_map": [
        {
            "role": "economic_buyer",
            "concern": "return on invested capital",
        }
    ],
}


def run_module(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_source_retraction_jobs_and_health_status_e2e() -> None:
    project = project_repository.create_project(
        name="Step 70 Source Retraction E2E Hardening",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    event_response = client.post(
        "/sources/events",
        headers=HEADERS,
        json={
            "project_id": project.project_id,
            "source_id": "source-step-70",
            "event_type": "retracted",
            "source_version": "v1",
            "classification": "public",
            "event_payload": {"reason": "publisher withdrew source"},
            "hmac_validated": True,
        },
    )

    assert event_response.status_code == 200, event_response.json()
    event_id = str(event_response.json()["event_id"])

    pending_status = client.get(
        f"/health/projects/{project.project_id}/source-retractions",
        headers={"accept": API_MEDIA_TYPE},
    )
    assert pending_status.status_code == 200, pending_status.json()
    assert pending_status.json()["blocked"] is True
    assert pending_status.json()["pending_count"] == 1

    pending_hard_gate = client.get(
        f"/health/projects/{project.project_id}/hard-gates",
        headers={"accept": API_MEDIA_TYPE},
    )
    assert pending_hard_gate.status_code == 200, pending_hard_gate.json()
    assert pending_hard_gate.json()["passed"] is False
    assert any(
        check["name"] == "no_pending_retraction_cascade"
        for check in pending_hard_gate.json()["failed_checks"]
    )

    source_job = run_module("jobs.source_retraction_job", "--limit", "50")
    assert source_job.returncode == 0, source_job.stderr
    assert "enqueued_source_retraction_events=" in source_job.stdout

    processed_event = SourceLifecycleEventRepository().get_event(event_id)
    assert processed_event.processing_status == "processed"

    outbox_rows = [
        row
        for row in OutboxRepository().list_project_rows(project.project_id)
        if row.operation_type == "source_retracted"
        and row.payload.get("source_lifecycle_event_id") == event_id
    ]
    assert len(outbox_rows) == 1
    assert outbox_rows[0].payload["source_id"] == "source-step-70"

    enqueued_outbox = client.get(
        f"/health/projects/{project.project_id}/outbox",
        headers={"accept": API_MEDIA_TYPE},
    )
    assert enqueued_outbox.status_code == 200, enqueued_outbox.json()
    assert enqueued_outbox.json()["blocked"] is True
    assert enqueued_outbox.json()["unprocessed_count"] == 1

    outbox_hard_gate = client.get(
        f"/health/projects/{project.project_id}/hard-gates",
        headers={"accept": API_MEDIA_TYPE},
    )
    assert outbox_hard_gate.status_code == 200, outbox_hard_gate.json()
    assert outbox_hard_gate.json()["passed"] is False
    assert any(
        check["name"] == "no_failed_or_unprocessed_outbox_items"
        for check in outbox_hard_gate.json()["failed_checks"]
    )

    outbox_worker_result = OutboxWorker(outbox_repository=OutboxRepository()).run_once(
        limit=50,
        project_id=project.project_id,
    )
    assert outbox_worker_result.scanned_count >= 1
    assert outbox_worker_result.processed_count >= 1
    assert outbox_worker_result.failed_count == 0

    final_retractions = client.get(
        f"/health/projects/{project.project_id}/source-retractions",
        headers={"accept": API_MEDIA_TYPE},
    )
    assert final_retractions.status_code == 200, final_retractions.json()
    assert final_retractions.json()["blocked"] is False
    assert final_retractions.json()["pending_count"] == 0
    assert final_retractions.json()["failed_count"] == 0

    final_outbox = client.get(
        f"/health/projects/{project.project_id}/outbox",
        headers={"accept": API_MEDIA_TYPE},
    )
    assert final_outbox.status_code == 200, final_outbox.json()
    assert final_outbox.json()["blocked"] is False
    assert final_outbox.json()["unprocessed_count"] == 0
    assert final_outbox.json()["failed_count"] == 0

    final_hard_gate = client.get(
        f"/health/projects/{project.project_id}/hard-gates",
        headers={"accept": API_MEDIA_TYPE},
    )
    assert final_hard_gate.status_code == 200, final_hard_gate.json()
    assert final_hard_gate.json()["passed"] is True
    assert final_hard_gate.json()["failed_checks"] == []
