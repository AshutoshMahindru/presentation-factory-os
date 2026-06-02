from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from agents.intake_agent import IntakeAgent
from agents.intake_chat_orchestrator import IntakeChatOrchestrator
from api.sources import router as sources_router
from api.project_repository import ProjectRepository
from system.audience_profile_validator import AudienceProfileValidator
from system.approval_quorum import ApprovalEntry, ApprovalQuorum
from system.chat_repository import ChatMessage, ChatRepository
from system.hard_gate_repository import HardGateRepository
from system.outbox_repository import OutboxRepository
from system.source_lifecycle_repository import SourceLifecycleRepository
from system.state_machine import GuardFailedError, StateMachine, StateMachineError



app = FastAPI(title="PFOS Workflow Service", version="3.2.4")
app.include_router(sources_router)

project_repository = ProjectRepository()
outbox_repository = OutboxRepository()
chat_repository = ChatRepository()
hard_gate_repository = HardGateRepository()
source_lifecycle_repository = SourceLifecycleRepository()


def create_thesis_repository() -> Any:
    from system.db import open_pool
    from system.thesis_repository import ThesisRepository

    return ThesisRepository(open_pool())


class DeterministicIntakeLLMClient:
    """Local fallback client used until a remotely configured intake model exists."""

    def complete(
        self, prompt: str, temperature: float = 0.0, max_tokens: int = 2000
    ) -> str:
        return json.dumps(
            {
                "project_updates": {},
                "audience_profile": {
                    "decision_maker_type": "ic_partner",
                    "risk_tolerance": "medium",
                    "familiarity_with_topic": "informed",
                    "known_objections": [],
                    "stakeholder_map": [
                        {
                            "role": "economic_buyer",
                            "concern": "Intake details incomplete",
                            "influence_level": "medium",
                        }
                    ],
                },
                "confidence": 0.2,
                "gaps": [
                    "Deterministic fallback needs more operator-provided intake context."
                ],
                "recommended_next_action": (
                    "Continue intake chat before applying project updates."
                ),
            },
            sort_keys=True,
        )


def chat_message_to_payload(message: ChatMessage | dict[str, Any]) -> dict[str, Any]:
    if isinstance(message, ChatMessage):
        return asdict(message)
    if is_dataclass(message):
        return asdict(message)  # type: ignore[arg-type]
    return dict(message)


class WorkflowChatClient:
    def __init__(self, repository: ChatRepository) -> None:
        self.repository = repository

    def append_intake_chat_message(
        self,
        project_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        return chat_message_to_payload(
            self.repository.append_message(
                project_id=project_id,
                role=role,
                content=content,
                metadata=metadata,
                actor_email=actor_email,
            )
        )

    def list_intake_chat_messages(
        self, project_id: str, limit: int = 100
    ) -> tuple[dict[str, Any], ...]:
        return tuple(
            chat_message_to_payload(message)
            for message in self.repository.list_messages(project_id, limit=limit)
        )


intake_chat_orchestrator = IntakeChatOrchestrator(
    workflow_client=WorkflowChatClient(chat_repository),
    intake_agent=IntakeAgent(DeterministicIntakeLLMClient()),
)


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


class SourceRetractionStatusResponse(BaseModel):
    project_id: str
    blocked: bool
    pending_count: int
    processing_count: int
    failed_count: int
    oldest_open_age_seconds: int | None = None


class HardGateStatusResponse(BaseModel):
    project_id: str
    name: str
    passed: bool
    checks: list[dict[str, Any]]
    failed_checks: list[dict[str, Any]]


class IntakeChatMessageRequest(BaseModel):
    content: str = Field(min_length=1)
    actor_email: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntakeChatMessageResponse(BaseModel):
    message_id: str
    project_id: str
    turn_index: int
    role: str
    content: str
    metadata: dict[str, Any]
    actor_email: str | None = None
    created_at: str


class IntakeChatMessagesResponse(BaseModel):
    project_id: str
    message_count: int
    messages: list[IntakeChatMessageResponse]


class IntakeChatTurnResponse(BaseModel):
    project_id: str
    status: str
    user_message: IntakeChatMessageResponse
    assistant_message: IntakeChatMessageResponse | None = None
    source_turn_count: int
    proposal: dict[str, Any]


class SourceCreateRequest(BaseModel):
    uri: str
    title: str | None = None
    source_type: str
    normalized_text: str


class ThesisVersionCreateRequest(BaseModel):
    thesis_statement: str
    pillars: list[dict[str, Any]]


class ResearchLoopStartRequest(BaseModel):
    loop_number: int
    sources_discovered_count: int = 0


class ResearchLoopFinalizeRequest(BaseModel):
    convergence_delta: float
    sources_discovered_count: int
    status: str


class ResearchDeepReadRequest(BaseModel):
    thesis_version_id: str


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


@app.get("/ready")
def ready() -> dict[str, str]:
    return {"service": "workflow-service", "status": "ready"}


@app.get("/metrics")
def get_metrics() -> Response:
    snapshot = project_repository.get_observability_metrics_snapshot()
    return Response(
        content=render_prometheus_metrics(snapshot),
        media_type="text/plain; version=0.0.4",
    )


@app.get("/traces/{project_id}")
def get_project_traces(project_id: str) -> dict[str, Any]:
    project = project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    return {
        "project_id": project_id,
        "traces": project_repository.list_phase_traces(project_id),
    }


@app.get("/observability/retrieval-routing/{project_id}")
def get_project_retrieval_routing(project_id: str) -> dict[str, Any]:
    project = project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    routing_logs = project_repository.list_retrieval_routing_logs(project_id)
    return {
        "project_id": project_id,
        "routing_log_count": len(routing_logs),
        "routing_logs": routing_logs,
    }


@app.get("/observability/rubric/{project_id}/{phase}")
def get_project_rubric_audit(project_id: str, phase: str) -> dict[str, Any]:
    project = project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    scores = project_repository.list_rubric_scores(project_id, phase)
    return {
        "project_id": project_id,
        "phase": phase,
        "score_count": len(scores),
        "scores": scores,
    }


def render_prometheus_metrics(snapshot: dict[str, Any]) -> str:
    metric_names = {
        "project_count": "pfos_projects_total",
        "phase_transition_count": "pfos_phase_transitions_total",
        "approval_count": "pfos_approvals_total",
        "open_outbox_count": "pfos_open_outbox_items",
        "failed_outbox_count": "pfos_failed_outbox_items",
        "open_source_retraction_count": "pfos_open_source_retractions",
        "retrieval_routing_log_count": "pfos_retrieval_routing_logs_total",
        "rubric_score_count": "pfos_rubric_scores_total",
    }
    lines: list[str] = []
    for key, metric_name in metric_names.items():
        value = int(snapshot.get(key, 0))
        metric_type = "counter" if metric_name.endswith("_total") else "gauge"
        lines.append(f"# HELP {metric_name} PFOS {key.replace('_', ' ')}.")
        lines.append(f"# TYPE {metric_name} {metric_type}")
        lines.append(f"{metric_name} {value}")
    return "\n".join(lines) + "\n"


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


@app.get(
    "/projects/{project_id}/intake-chat/messages",
    response_model=IntakeChatMessagesResponse,
)
def list_intake_chat_messages(
    project_id: str,
    limit: int = 100,
    after_turn_index: int | None = None,
) -> IntakeChatMessagesResponse:
    project = project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    try:
        messages = [
            IntakeChatMessageResponse(**chat_message_to_payload(message))
            for message in chat_repository.list_messages(
                project_id=project_id,
                limit=limit,
                after_turn_index=after_turn_index,
            )
        ]
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_chat_query", "message": str(exc)},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "chat_repository_unavailable", "message": str(exc)},
        ) from exc

    return IntakeChatMessagesResponse(
        project_id=project_id,
        message_count=len(messages),
        messages=messages,
    )


@app.post(
    "/projects/{project_id}/intake-chat",
    response_model=IntakeChatTurnResponse,
)
@app.post(
    "/projects/{project_id}/intake-chat/messages",
    response_model=IntakeChatTurnResponse,
)
def append_intake_chat_message(
    project_id: str,
    payload: IntakeChatMessageRequest,
) -> IntakeChatTurnResponse:
    project = project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    if project.current_phase != "intake":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "phase_mismatch",
                "current_phase": project.current_phase,
                "required_phase": "intake",
            },
        )

    try:
        result = intake_chat_orchestrator.handle_user_message(
            project_id=project_id,
            content=payload.content,
            actor_email=payload.actor_email,
            metadata=payload.metadata,
        )
        result_payload = result.to_payload()
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_chat_message", "message": str(exc)},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "intake_chat_unavailable", "message": str(exc)},
        ) from exc

    return IntakeChatTurnResponse(
        project_id=str(result_payload["project_id"]),
        status=str(result_payload["status"]),
        user_message=IntakeChatMessageResponse(
            **chat_message_to_payload(result_payload["user_message"])
        ),
        assistant_message=(
            IntakeChatMessageResponse(
                **chat_message_to_payload(result_payload["assistant_message"])
            )
            if result_payload.get("assistant_message") is not None
            else None
        ),
        source_turn_count=int(result_payload["source_turn_count"]),
        proposal=dict(result_payload["proposal"]),
    )


@app.get("/health/projects/{project_id}/source-retractions", response_model=SourceRetractionStatusResponse)
def get_project_source_retraction_status(project_id: str) -> SourceRetractionStatusResponse:
    project = project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    status = source_lifecycle_repository.get_project_retraction_cascade_status(project_id)

    return SourceRetractionStatusResponse(
        project_id=project_id,
        blocked=status.blocked,
        pending_count=status.pending_count,
        processing_count=status.processing_count,
        failed_count=status.failed_count,
        oldest_open_age_seconds=status.oldest_open_age_seconds,
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


@app.get("/health/projects/{project_id}/hard-gates", response_model=HardGateStatusResponse)
def get_project_hard_gate_status(project_id: str) -> HardGateStatusResponse:
    project = project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    result = hard_gate_repository.evaluate_no_blocking_rules(project_id)
    payload = result.as_payload()

    return HardGateStatusResponse(
        project_id=project_id,
        name=str(payload["name"]),
        passed=bool(payload["passed"]),
        checks=list(payload["checks"]),
        failed_checks=list(payload["failed_checks"]),
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


@app.post("/projects/{project_id}/sources")
def create_project_source(
    project_id: str,
    payload: SourceCreateRequest,
) -> dict[str, Any]:
    from system.db import open_pool
    from system.source_register_repository import SourceRegisterRepository

    repository = SourceRegisterRepository(open_pool())
    row = repository.create(
        project_id=UUID(project_id),
        uri=payload.uri,
        title=payload.title,
        source_type=payload.source_type,
        normalized_text=payload.normalized_text,
    )
    return {"id": str(row.id), "status": "created", "uri": payload.uri}


@app.post("/projects/{project_id}/thesis-versions")
def create_project_thesis_version(
    project_id: str,
    payload: ThesisVersionCreateRequest,
) -> dict[str, Any]:
    repository = create_thesis_repository()
    version = repository.create_thesis_version(
        UUID(project_id),
        1,
        payload.thesis_statement,
    )
    for pillar in payload.pillars:
        repository.create_pillar(
            version.id,
            int(pillar["pillar_index"]),
            str(pillar["pillar_type"]),
            str(pillar["statement"]),
        )

    return {"id": str(version.id), "version_number": version.version_number}


@app.get("/projects/{project_id}/thesis-versions/current")
def get_current_thesis_version(project_id: str) -> dict[str, Any] | None:
    repository = create_thesis_repository()
    version = repository.get_latest_thesis(UUID(project_id))
    if version is None:
        return None

    pillars = repository.get_pillars(version.id)
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "thesis_statement": version.thesis_statement,
        "convergence_score": version.convergence_score,
        "pillars": [
            {
                "id": str(pillar.id),
                "pillar_index": pillar.pillar_index,
                "pillar_type": pillar.pillar_type,
                "statement": pillar.statement,
                "stress_status": pillar.stress_status,
            }
            for pillar in pillars
        ],
    }


def _neo4j_run_cypher(query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    import os

    from neo4j import GraphDatabase

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD") or "pfos_neo4j_password"
    database = os.environ.get("NEO4J_DATABASE") or None

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]
    finally:
        driver.close()


@app.post("/projects/{project_id}/research-loops/start")
@app.post("/research-loops/start")
def start_research_loop(
    project_id: str | None = None,
    payload: ResearchLoopStartRequest | None = None,
) -> dict[str, Any]:
    if payload is None:
        raise HTTPException(status_code=422, detail={"error": "missing_payload"})
    if project_id is None:
        project_id = "00000000-0000-0000-0000-000000000000"

    repository = create_thesis_repository()
    loop = repository.start_research_loop(UUID(project_id), payload.loop_number)
    return {
        "id": str(loop.id),
        "loop_number": loop.loop_number,
        "status": loop.status,
    }


@app.post("/projects/{project_id}/research-loops/{loop_id}/finalize")
@app.post("/research-loops/{loop_id}/finalize")
def finalize_research_loop(
    loop_id: str,
    payload: ResearchLoopFinalizeRequest,
    project_id: str | None = None,
) -> dict[str, Any]:
    repository = create_thesis_repository()
    repository.finalize_research_loop(
        UUID(loop_id),
        payload.convergence_delta,
        payload.sources_discovered_count,
        payload.status,
    )
    return {
        "id": loop_id,
        "status": payload.status,
        "convergence_delta": payload.convergence_delta,
    }


@app.post("/projects/{project_id}/research/deep-read-sources")
def deep_read_sources_for_pillars(
    project_id: str,
    payload: ResearchDeepReadRequest,
) -> dict[str, Any]:
    from evidence_graph.evidence_linker import deep_read_sources_for_pillars
    from system.db import open_pool

    result = deep_read_sources_for_pillars(
        open_pool(),
        _neo4j_run_cypher,
        project_id=project_id,
        thesis_version_id=payload.thesis_version_id,
    )

    return {
        "project_id": result.project_id,
        "thesis_version_id": result.thesis_version_id,
        "pillar_links": [
            {
                "pillar_id": link.pillar_id,
                "pillar_index": link.pillar_index,
                "pillar_type": link.pillar_type,
                "statement": link.statement,
                "source_ids": list(link.source_ids),
            }
            for link in result.pillar_links
        ],
        "total_sources": result.total_sources(),
        "pillars_with_no_sources": list(result.pillar_ids_with_no_sources()),
    }


@app.post(
    "/projects/{project_id}/thesis-versions/{thesis_version_id}/financial-review-context"
)
def financial_review_context(
    project_id: str,
    thesis_version_id: str,
) -> dict[str, Any]:
    """Return thesis pillars and active financial cells for review."""
    from uuid import UUID

    from system.db import open_pool
    from system.financial_repository import FinancialRepository
    from system.thesis_repository import ThesisRepository

    pool = open_pool()
    thesis_repo = ThesisRepository(pool)
    financial_repo = FinancialRepository(pool)

    pillars = thesis_repo.get_pillars(UUID(thesis_version_id))
    cells_by_pillar: dict[str, list[dict[str, Any]]] = {}
    for pillar in pillars:
        cells = financial_repo.list_cells_for_pillar(pillar.id)
        cells_by_pillar[str(pillar.id)] = [
            {
                "id": str(cell.id),
                "cell_ref": cell.cell_ref,
                "label": cell.label,
                "value": float(cell.value),
                "unit": cell.unit,
                "scenario": cell.scenario,
                "formula": cell.formula,
                "artifact_status": cell.artifact_status,
            }
            for cell in cells
            if cell.artifact_status == "active"
        ]

    return {
        "project_id": project_id,
        "thesis_version_id": thesis_version_id,
        "pillars": [
            {
                "id": str(pillar.id),
                "pillar_index": pillar.pillar_index,
                "pillar_type": pillar.pillar_type,
                "statement": pillar.statement,
                "stress_status": pillar.stress_status,
            }
            for pillar in pillars
        ],
        "cells_by_pillar": cells_by_pillar,
    }
