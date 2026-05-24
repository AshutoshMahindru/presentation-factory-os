from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from system.outbox_repository import PendingOutboxRow


@dataclass(frozen=True)
class Neo4jRetractionHandlerResult:
    project_id: str
    source_id: str
    source_lifecycle_event_id: str
    operation_type: str
    applied: bool


class Neo4jSourceRetractionHandler:
    """
    Deterministic handler stub for source_retracted outbox rows.

    Baby Step 55 intentionally does not write source retraction effects to Neo4j yet.
    It validates the outbox payload contract and returns deterministic success so
    the outbox worker can process source_retracted operations end-to-end.
    """

    REQUIRED_PAYLOAD_KEYS = {
        "source_lifecycle_event_id",
        "project_id",
        "source_id",
        "event_type",
    }

    def __call__(self, row: PendingOutboxRow) -> Neo4jRetractionHandlerResult:
        return self.handle(row)

    def handle(self, row: PendingOutboxRow) -> Neo4jRetractionHandlerResult:
        if row.target_store != "neo4j":
            raise ValueError(f"Unsupported target_store for Neo4j handler: {row.target_store}")

        if row.operation_type != "source_retracted":
            raise ValueError(
                f"Unsupported operation_type for source retraction handler: {row.operation_type}"
            )

        self._validate_payload(row.payload)

        if row.payload["event_type"] != "retracted":
            raise ValueError("source_retracted outbox payload must have event_type='retracted'")

        if row.payload["project_id"] != row.project_id:
            raise ValueError("source_retracted outbox payload project_id must match row.project_id")

        return Neo4jRetractionHandlerResult(
            project_id=str(row.payload["project_id"]),
            source_id=str(row.payload["source_id"]),
            source_lifecycle_event_id=str(row.payload["source_lifecycle_event_id"]),
            operation_type=row.operation_type,
            applied=True,
        )

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        missing = sorted(self.REQUIRED_PAYLOAD_KEYS - set(payload))
        if missing:
            raise ValueError(f"source_retracted outbox payload missing required keys: {missing}")

        for key in self.REQUIRED_PAYLOAD_KEYS:
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"source_retracted outbox payload field must be a non-empty string: {key}"
                )
