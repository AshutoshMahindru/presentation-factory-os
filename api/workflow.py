from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from api.project_repository import ProjectRepository
from system.audience_profile_validator import AudienceProfileValidator
from system.approval_quorum import ApprovalEntry, ApprovalQuorum
from system.outbox_repository import OutboxRepository
from system.state_machine import GuardFailedError, StateMachine, StateMachineError



app = FastAPI(title="PFOS Workflow Service", version="3.2.4")

project_repository = ProjectRepository()
outbox_repository = OutboxRepository()


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    audience_profile: dict[str, Any]
    client_name: str | None = None
    decision_required: str | None = None
    objection_preemption_map: dict[str, Any] = Field(default_factory=dict)


class CreateProjectResponse(BaseModel):
    project_id: str
    phase: str
    audience_profile_valid: bool


class PhaseTransitionRequest(BaseModel):
    from_phase: str
    to_phase: str
    transition_kind: str
    requested_by: str = Field(min_length=1)
    reason: str | None = None
    guard_context: dict[str, Any] = Field(default_factory=dict)


class ApprovalSubmissionRequest(BaseModel):
    phase: str
    actor_email: str = Field(min_length=1)
    role: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    rubric_score_snapshot: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None



class ApprovalStatusResponse(BaseModel):
    project_id: str
    phase: str
    quorum_met: bool
    decision_rule: str
    required_count: int
    approved_count: int
    rejected_count: int
    abstained_count: int
    changes_requested_count: int
    missing_roles: dict[str, int]
    blocking_rejection: bool
    escalation_status: str
    escalation_reason: str | None = None



class OutboxStatusResponse(BaseModel):
    project_id: str
    blocked: bool
    unprocessed_count: int
    failed_count: int
    oldest_unprocessed_age_seconds: int | None = None


def approval_escalation_status(approvals: list[dict[str, Any]], blocking_rejection: bool) -> tuple[str, str | None]:
    if any(
        approval["role"] == "senior_partner" and approval["decision"] == "rejected"
        for approval in approvals
    ):
        return "attention_required", "rejection_by_senior_partner"

    if any(approval["decision"] == "changes_requested" for approval in approvals):
        return "attention_required", "changes_requested"

    if blocking_rejection:
        return "attention_required", "review_rejection"

    return "none", None


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "workflow-service", "status": "ok"}


@app.post("/projects", response_model=CreateProjectResponse)
def create_project(payload: CreateProjectRequest) -> CreateProjectResponse:
    audience_validator = AudienceProfileValidator.from_file()
    audience_result = audience_validator.validate(payload.audience_profile)

    if not audience_result.valid:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_failed",
                "message": "; ".join(audience_result.errors),
                "blocking_gate": "audience_psychology_adequate",
            },
        )

    project = project_repository.create_project(
        name=payload.name,
        audience=payload.audience,
        audience_profile=payload.audience_profile,
        client_name=payload.client_name,
        decision_required=payload.decision_required,
        objection_preemption_map=payload.objection_preemption_map,
    )

    return CreateProjectResponse(
        project_id=project.project_id,
        phase=project.current_phase,
        audience_profile_valid=True,
    )


@app.get("/health/projects/{project_id}/outbox", response_model=OutboxStatusResponse)
def get_project_outbox_status(project_id: str) -> OutboxStatusResponse:
    project = project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    status = outbox_repository.get_project_outbox_status(project_id)

    return OutboxStatusResponse(
        project_id=project_id,
        blocked=status.blocked,
        unprocessed_count=status.unprocessed_count,
        failed_count=status.failed_count,
        oldest_unprocessed_age_seconds=status.oldest_unprocessed_age_seconds,
    )


@app.get("/projects/{project_id}/approvals/status/{phase}", response_model=ApprovalStatusResponse)
def get_approval_status(project_id: str, phase: str) -> ApprovalStatusResponse:
    project = project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    approvals = project_repository.list_approvals_for_phase(project_id, phase)
    entries = [
        ApprovalEntry(
            actor_email=approval["actor_email"],
            role=approval["role"],
            decision=approval["decision"],
        )
        for approval in approvals
    ]

    try:
        quorum_result = ApprovalQuorum.from_yaml().evaluate(phase, entries)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "approval_status_unavailable",
                "project_id": project_id,
                "phase": phase,
                "message": str(exc),
            },
        ) from exc

    escalation_status, escalation_reason = approval_escalation_status(
        approvals=approvals,
        blocking_rejection=quorum_result.blocking_rejection,
    )

    return ApprovalStatusResponse(
        project_id=project_id,
        phase=phase,
        quorum_met=quorum_result.quorum_met,
        decision_rule=quorum_result.decision_rule,
        required_count=quorum_result.required_count,
        approved_count=quorum_result.approved_count,
        rejected_count=quorum_result.rejected_count,
        abstained_count=quorum_result.abstained_count,
        changes_requested_count=quorum_result.changes_requested_count,
        missing_roles=quorum_result.missing_roles,
        blocking_rejection=quorum_result.blocking_rejection,
        escalation_status=escalation_status,
        escalation_reason=escalation_reason,
    )


@app.post("/projects/{project_id}/phase-transitions")
def request_phase_transition(project_id: str, payload: PhaseTransitionRequest) -> dict[str, Any]:
    project = project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    if project.current_phase != payload.from_phase:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "phase_mismatch",
                "current_phase": project.current_phase,
                "requested_from_phase": payload.from_phase,
            },
        )

    outbox_status = outbox_repository.get_project_outbox_status(project_id)
    if outbox_status.blocked:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "transition_blocked",
                "project_id": project_id,
                "from_phase": payload.from_phase,
                "to_phase": payload.to_phase,
                "blocking_guards": [
                    {
                        "name": "no_failed_or_unprocessed_outbox_items",
                        "reason": "project_has_failed_or_unprocessed_outbox_rows",
                        "unprocessed_count": outbox_status.unprocessed_count,
                        "failed_count": outbox_status.failed_count,
                        "oldest_unprocessed_age_seconds": outbox_status.oldest_unprocessed_age_seconds,
                    }
                ],
            },
        )

    context = {
        "project": {
            "project_id": project.project_id,
            "audience_profile": project.audience_profile,
        },
        "transition": {
            "from_phase": payload.from_phase,
            "to_phase": payload.to_phase,
            "kind": payload.transition_kind,
        },
        "guards": payload.guard_context.get("guards", {}),
    }

    state_machine = StateMachine.from_yaml()

    try:
        transition, guard_results = state_machine.validate_transition_with_guards(
            from_phase=payload.from_phase,
            to_phase=payload.to_phase,
            kind=payload.transition_kind,  # type: ignore[arg-type]
            context=context,
            reason=payload.reason,
        )
    except GuardFailedError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "transition_blocked",
                "project_id": project_id,
                "from_phase": payload.from_phase,
                "to_phase": payload.to_phase,
                "blocking_guards": [
                    {
                        "name": guard.name,
                        "reason": guard.reason,
                    }
                    for guard in exc.failed_guards
                ],
            },
        ) from exc
    except StateMachineError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_transition",
                "message": str(exc),
            },
        ) from exc

    serialized_guard_results = [
        {
            "name": result.name,
            "status": "pass" if result.passed else "fail",
            "reason": result.reason,
        }
        for result in guard_results
    ]

    transition_id = str(uuid4())

    project_repository.record_phase_transition(
        project_id=project_id,
        from_phase=transition.from_phase,
        to_phase=transition.to_phase,
        transition_kind=transition.kind,
        guard_results=serialized_guard_results,
        hard_gate_results={},
        state_machine_version=state_machine.version,
        reason=payload.reason,
        actor_email=payload.requested_by,
    )

    project_repository.update_phase(project_id, transition.to_phase)

    return {
        "transition_id": transition_id,
        "project_id": project_id,
        "from_phase": transition.from_phase,
        "to_phase": transition.to_phase,
        "status": "applied",
        "guards": serialized_guard_results,
    }


@app.post("/projects/{project_id}/approvals")
def submit_approval(project_id: str, payload: ApprovalSubmissionRequest) -> dict[str, Any]:
    project = project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    try:
        project_repository.record_approval(
            project_id=project_id,
            phase=payload.phase,
            actor_email=payload.actor_email,
            role=payload.role,
            decision=payload.decision,
            rubric_score_snapshot=payload.rubric_score_snapshot,
            notes=payload.notes,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "approval_rejected",
                "message": str(exc),
            },
        ) from exc

    approvals = project_repository.list_approvals_for_phase(project_id, payload.phase)
    entries = [
        ApprovalEntry(
            actor_email=item["actor_email"],
            role=item["role"],
            decision=item["decision"],
        )
        for item in approvals
    ]

    try:
        quorum_result = ApprovalQuorum.from_yaml().evaluate(payload.phase, entries)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "quorum_evaluation_failed",
                "message": str(exc),
            },
        ) from exc

    return {
        "project_id": project_id,
        "phase": payload.phase,
        "approval_recorded": True,
        "quorum_met": quorum_result.quorum_met,
        "approved_count": quorum_result.approved_count,
        "rejected_count": quorum_result.rejected_count,
        "changes_requested_count": quorum_result.changes_requested_count,
        "missing_roles": quorum_result.missing_roles,
        "blocking_rejection": quorum_result.blocking_rejection,
    }

# --- Step 103: Source discovery endpoint ---

from pydantic import BaseModel
from typing import Any

class SourceCreateRequest(BaseModel):
    uri: str
    title: str | None = None
    source_type: str
    normalized_text: str

@app.post("/projects/{project_id}/sources")
async def create_project_source(
    project_id: str,
    req: SourceCreateRequest,
) -> dict[str, Any]:
    from system.source_register_repository import SourceRegisterRepository
    repo = SourceRegisterRepository(db_pool)  # type: ignore[name-defined]
    row = repo.create(
        project_id=project_id,
        uri=req.uri,
        title=req.title,
        source_type=req.source_type,
        normalized_text=req.normalized_text,
    )
    return {"id": str(row.id), "status": "created", "uri": req.uri}


# --- Step 105: Thesis version endpoints ---

class ThesisVersionCreateRequest(BaseModel):
    thesis_statement: str
    pillars: list[dict[str, Any]]

class ThesisPillarCreate(BaseModel):
    pillar_index: int
    pillar_type: str
    statement: str

@app.post("/projects/{project_id}/thesis-versions")
async def create_project_thesis_version(
    project_id: str,
    req: ThesisVersionCreateRequest,
) -> dict[str, Any]:
    from system.thesis_repository import ThesisRepository
    repo = ThesisRepository(db_pool)  # type: ignore[name-defined]
    version = repo.create_thesis_version(project_id, 1, req.thesis_statement)

    for p in req.pillars:
        repo.create_pillar(
            version.id,
            p["pillar_index"],
            p["pillar_type"],
            p["statement"],
        )

    return {"id": str(version.id), "version_number": version.version_number}

@app.get("/projects/{project_id}/thesis-versions/current")
async def get_current_thesis_version(project_id: str) -> dict[str, Any] | None:
    from system.thesis_repository import ThesisRepository
    repo = ThesisRepository(db_pool)  # type: ignore[name-defined]
    version = repo.get_latest_thesis(project_id)
    if not version:
        return None

    pillars = repo.get_pillars(version.id)
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "thesis_statement": version.thesis_statement,
        "convergence_score": version.convergence_score,
        "pillars": [
            {
                "id": str(p.id),
                "pillar_index": p.pillar_index,
                "pillar_type": p.pillar_type,
                "statement": p.statement,
                "stress_status": p.stress_status,
            }
            for p in pillars
        ],
    }

