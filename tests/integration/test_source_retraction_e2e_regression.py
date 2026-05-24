from __future__ import annotations

from api.workflow import project_repository
from jobs.outbox_worker import OutboxWorker
from jobs.source_retraction_job import SourceRetractionJob
from system.hard_gate_repository import HardGateRepository
from system.outbox_repository import OutboxRepository
from system.source_lifecycle_event_repository import SourceLifecycleEventRepository


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


def test_source_retraction_lifecycle_event_flows_through_jobs_and_unblocks_hard_gate() -> None:
    project = project_repository.create_project(
        name="Step 56 Source Retraction E2E",
        audience="Investment committee",
        audience_profile=VALID_AUDIENCE_PROFILE,
    )

    source_event_repository = SourceLifecycleEventRepository()
    outbox_repository = OutboxRepository()
    hard_gate_repository = HardGateRepository()

    event = source_event_repository.create_event(
        project_id=project.project_id,
        source_id="source-e2e-1",
        event_type="retracted",
        event_payload={"reason": "publisher withdrew source"},
        source_version="v1",
        classification="public",
        hmac_validated=True,
        processing_status="pending",
    )

    initial_gate = hard_gate_repository.evaluate_no_blocking_rules(project.project_id)
    assert initial_gate.passed is False
    assert any(
        check.name == "no_pending_retraction_cascade"
        and check.reason == "project_has_open_retraction_cascade_events"
        for check in initial_gate.failed_checks
    )

    source_job_result = SourceRetractionJob(
        source_lifecycle_event_repository=source_event_repository,
        outbox_repository=outbox_repository,
    ).run_once(limit=50)

    assert source_job_result.scanned_count >= 1
    assert source_job_result.enqueued_count >= 1
    assert source_job_result.failed_count == 0

    processed_event = source_event_repository.get_event(event.event_id)
    assert processed_event.processing_status == "processed"

    outbox_rows = [
        row
        for row in outbox_repository.list_project_rows(project.project_id)
        if row.operation_type == "source_retracted"
        and row.payload.get("source_lifecycle_event_id") == event.event_id
    ]

    assert len(outbox_rows) == 1
    assert outbox_rows[0].payload["source_id"] == "source-e2e-1"

    blocked_by_outbox = hard_gate_repository.evaluate_no_blocking_rules(project.project_id)
    assert blocked_by_outbox.passed is False
    assert any(
        check.name == "no_failed_or_unprocessed_outbox_items"
        and check.reason == "project_has_failed_or_unprocessed_outbox_rows"
        for check in blocked_by_outbox.failed_checks
    )

    outbox_worker_result = OutboxWorker(outbox_repository=outbox_repository).run_once(
        limit=50,
        project_id=project.project_id,
    )

    assert outbox_worker_result.scanned_count >= 1
    assert outbox_worker_result.processed_count >= 1
    assert outbox_worker_result.failed_count == 0

    final_gate = hard_gate_repository.evaluate_no_blocking_rules(project.project_id)
    assert final_gate.passed is True
    assert final_gate.failed_checks == ()
