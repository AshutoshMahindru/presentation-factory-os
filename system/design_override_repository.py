from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any


@dataclass(frozen=True)
class DesignOverrideRecord:
    override_id: str
    project_id: str
    slide_id: str
    field_path: str
    old_value: Any
    new_value: Any
    actor: str
    reason: str
    triggers_reapproval: bool
    created_at: str


class DesignOverrideRepository:
    def __init__(self) -> None:
        self._records: list[DesignOverrideRecord] = []

    def record_override(
        self,
        *,
        project_id: str,
        slide_id: str,
        field_path: str,
        old_value: Any,
        new_value: Any,
        actor: str,
        reason: str,
    ) -> DesignOverrideRecord:
        if not reason.strip():
            raise ValueError("override reason is required")
        if old_value == new_value:
            raise ValueError("override must change the value")
        created_at = datetime.now(UTC).isoformat()
        seed = f"{project_id}|{slide_id}|{field_path}|{old_value!r}|{new_value!r}|{actor}|{created_at}"
        record = DesignOverrideRecord(
            override_id=sha256(seed.encode("utf-8")).hexdigest()[:16],
            project_id=project_id,
            slide_id=slide_id,
            field_path=field_path,
            old_value=old_value,
            new_value=new_value,
            actor=actor,
            reason=reason,
            triggers_reapproval=True,
            created_at=created_at,
        )
        self._records.append(record)
        return record

    def list_project_overrides(self, project_id: str) -> list[DesignOverrideRecord]:
        return [record for record in self._records if record.project_id == project_id]
