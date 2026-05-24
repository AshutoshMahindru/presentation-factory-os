from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.project_repository import project_repository
from system.source_lifecycle_event_repository import SourceLifecycleEventRepository


router = APIRouter()

source_lifecycle_event_repository = SourceLifecycleEventRepository()


class SourceLifecycleEventRequest(BaseModel):
    project_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    source_version: str | None = None
    classification: str | None = None
    event_payload: dict[str, Any] = Field(default_factory=dict)
    hmac_validated: bool = False


class SourceLifecycleEventResponse(BaseModel):
    event_id: str
    project_id: str
    source_id: str
    event_type: str
    processing_status: str


@router.post("/sources/events", response_model=SourceLifecycleEventResponse)
def create_source_lifecycle_event(payload: SourceLifecycleEventRequest) -> SourceLifecycleEventResponse:
    project = project_repository.get_project(payload.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})

    try:
        event = source_lifecycle_event_repository.create_event(
            project_id=payload.project_id,
            source_id=payload.source_id,
            event_type=payload.event_type,
            event_payload=payload.event_payload,
            source_version=payload.source_version,
            classification=payload.classification,
            hmac_validated=payload.hmac_validated,
            processing_status="pending",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_source_lifecycle_event",
                "message": str(exc),
            },
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "source_lifecycle_event_write_failed",
                "message": str(exc),
            },
        ) from exc

    return SourceLifecycleEventResponse(
        event_id=event.event_id,
        project_id=event.project_id,
        source_id=event.source_id,
        event_type=event.event_type,
        processing_status=event.processing_status,
    )
