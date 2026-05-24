from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from system.audience_profile_validator import AudienceProfileValidator
from system.state_machine import GuardFailedError, StateMachine, StateMachineError


app = FastAPI(title="PFOS Workflow Service", version="3.2.4")

PROJECTS: dict[str, dict[str, Any]] = {}


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

    project_id = str(uuid4())
    PROJECTS[project_id] = {
        "project_id": project_id,
        "name": payload.name,
        "audience": payload.audience,
        "audience_profile": payload.audience_profile,
        "client_name": payload.client_name,
        "decision_required": payload.decision_required,
        "objection_preemption_map": payload.objection_preemption_map,
        "current_phase": "created",
    }

    return CreateProjectResponse(
        project_id=project_id,
        phase="created",
        audience_profile_valid=True,
    )


@app.post("/projects/{project_id}/phase-transitions")
def request_phase_transition(project_id: str, payload: PhaseTransitionRequest) -> dict[str, Any]:
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    project = PROJECTS[project_id]

    if project["current_phase"] != payload.from_phase:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "phase_mismatch",
                "current_phase": project["current_phase"],
                "requested_from_phase": payload.from_phase,
            },
        )

    context = {
        "project": {
            "audience_profile": project["audience_profile"],
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

    project["current_phase"] = transition.to_phase

    return {
        "transition_id": str(uuid4()),
        "project_id": project_id,
        "from_phase": transition.from_phase,
        "to_phase": transition.to_phase,
        "status": "applied",
        "guards": [
            {
                "name": result.name,
                "status": "pass" if result.passed else "fail",
                "reason": result.reason,
            }
            for result in guard_results
        ],
    }
