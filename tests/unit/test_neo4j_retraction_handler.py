from __future__ import annotations

import pytest

from system.neo4j_retraction_handler import Neo4jSourceRetractionHandler
from system.outbox_repository import PendingOutboxRow


def make_row(
    payload: dict[str, object] | None = None,
    target_store: str = "neo4j",
    operation_type: str = "source_retracted",
    project_id: str = "project-1",
) -> PendingOutboxRow:
    return PendingOutboxRow(
        outbox_id="outbox-1",
        project_id=project_id,
        target_store=target_store,
        operation_type=operation_type,
        payload=payload
        or {
            "source_lifecycle_event_id": "event-1",
            "project_id": "project-1",
            "source_id": "source-1",
            "event_type": "retracted",
        },
        error_count=0,
    )


def test_neo4j_source_retraction_handler_accepts_valid_payload() -> None:
    handler = Neo4jSourceRetractionHandler()

    result = handler(make_row())

    assert result.project_id == "project-1"
    assert result.source_id == "source-1"
    assert result.source_lifecycle_event_id == "event-1"
    assert result.operation_type == "source_retracted"
    assert result.applied is True


def test_neo4j_source_retraction_handler_rejects_wrong_target_store() -> None:
    handler = Neo4jSourceRetractionHandler()

    with pytest.raises(ValueError, match="Unsupported target_store"):
        handler(make_row(target_store="postgres"))


def test_neo4j_source_retraction_handler_rejects_wrong_operation_type() -> None:
    handler = Neo4jSourceRetractionHandler()

    with pytest.raises(ValueError, match="Unsupported operation_type"):
        handler(make_row(operation_type="claim_updated"))


def test_neo4j_source_retraction_handler_rejects_missing_payload_key() -> None:
    handler = Neo4jSourceRetractionHandler()
    payload = {
        "project_id": "project-1",
        "source_id": "source-1",
        "event_type": "retracted",
    }

    with pytest.raises(ValueError, match="missing required keys"):
        handler(make_row(payload=payload))


def test_neo4j_source_retraction_handler_rejects_blank_payload_value() -> None:
    handler = Neo4jSourceRetractionHandler()
    payload = {
        "source_lifecycle_event_id": "",
        "project_id": "project-1",
        "source_id": "source-1",
        "event_type": "retracted",
    }

    with pytest.raises(ValueError, match="non-empty string"):
        handler(make_row(payload=payload))


def test_neo4j_source_retraction_handler_rejects_non_retracted_event_type() -> None:
    handler = Neo4jSourceRetractionHandler()
    payload = {
        "source_lifecycle_event_id": "event-1",
        "project_id": "project-1",
        "source_id": "source-1",
        "event_type": "updated",
    }

    with pytest.raises(ValueError, match="event_type='retracted'"):
        handler(make_row(payload=payload))


def test_neo4j_source_retraction_handler_rejects_mismatched_project_id() -> None:
    handler = Neo4jSourceRetractionHandler()
    payload = {
        "source_lifecycle_event_id": "event-1",
        "project_id": "other-project",
        "source_id": "source-1",
        "event_type": "retracted",
    }

    with pytest.raises(ValueError, match="project_id must match"):
        handler(make_row(payload=payload, project_id="project-1"))
