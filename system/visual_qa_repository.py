from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class VisualQARecord:
    project_id: str
    artifact_id: str
    status: str
    score: float
    findings: tuple[str, ...]
    created_at: str


class InMemoryVisualQARepository:
    """Small repository contract for deterministic tests and local workflows."""

    def __init__(self) -> None:
        self._records: list[VisualQARecord] = []

    def record_result(
        self,
        *,
        project_id: str,
        artifact_id: str,
        status: str,
        score: float,
        findings: tuple[str, ...] | list[str] = (),
    ) -> VisualQARecord:
        if status not in {"passed", "failed"}:
            raise ValueError("status must be passed or failed")
        record = VisualQARecord(
            project_id=project_id,
            artifact_id=artifact_id,
            status=status,
            score=float(score),
            findings=tuple(findings),
            created_at=datetime.now(UTC).isoformat(),
        )
        self._records.append(record)
        return record

    def latest_for_artifact(self, project_id: str, artifact_id: str) -> VisualQARecord | None:
        for record in reversed(self._records):
            if record.project_id == project_id and record.artifact_id == artifact_id:
                return record
        return None

    def list_project_results(self, project_id: str) -> list[dict[str, Any]]:
        return [record.__dict__ for record in self._records if record.project_id == project_id]
