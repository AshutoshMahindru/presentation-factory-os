from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest

from financial_model.validator import FinancialValidationError
from system.financial_spec_repository import FinancialSpecRepository, FinancialSpecRow


class _SandboxRepository(FinancialSpecRepository):
    def __init__(self, row: FinancialSpecRow | None) -> None:
        self.row = row
        self.promoted_payload: dict[str, Any] | None = None

    def get_spec(self, spec_id):  # type: ignore[no-untyped-def]
        return self.row if self.row is not None and spec_id == self.row.id else None

    def mark_promoted(self, spec_id, promoted_to):  # type: ignore[no-untyped-def]
        assert self.row is not None
        assert spec_id == self.row.id
        self.promoted_payload = promoted_to
        self.row = replace(self.row, status="promoted", promoted_to=promoted_to)


class _RecordingFinancialRepository:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

    def upsert_cell(self, **kwargs: Any) -> object:
        self.upserts.append(kwargs)
        return object()


def _validated_spec(*, spec_json: dict[str, Any]) -> FinancialSpecRow:
    return FinancialSpecRow(
        id=uuid4(),
        project_id=uuid4(),
        thesis_pillar_id=uuid4(),
        name="Sandbox model",
        spec_json=spec_json,
        status="validated",
        validation_errors=[],
        promoted_to=None,
        created_at="2026-06-03T00:00:00Z",
        updated_at="2026-06-03T00:00:00Z",
    )


def _valid_cell(project_id: object, *, cell_ref: str = "Revenue") -> dict[str, Any]:
    return {
        "project_id": str(project_id),
        "scenario": "base",
        "cell_ref": cell_ref,
        "label": cell_ref,
        "value": 100.0,
        "formula": "100",
        "ingestion_source_type": "manual_compiler",
        "parser_provenance": {"parser_name": "pfos_spec_compiler"},
        "artifact_status": "active",
    }


def test_sandbox_promotion_rejects_missing_compiled_cells() -> None:
    spec = _validated_spec(spec_json={"scenario": "base"})
    repo = _SandboxRepository(spec)
    canonical = _RecordingFinancialRepository()

    with pytest.raises(ValueError, match="non-empty compiled_cells"):
        repo.promote_validated_spec_to_financial_cells(spec.id, canonical)

    assert canonical.upserts == []
    assert repo.promoted_payload is None
    assert repo.row is not None
    assert repo.row.status == "validated"


def test_sandbox_promotion_validates_cells_before_upsert() -> None:
    spec = _validated_spec(spec_json={})
    spec = replace(
        spec,
        spec_json={
            "compiled_cells": [
                {
                    **_valid_cell(spec.project_id),
                    "formula": "",
                }
            ]
        },
    )
    repo = _SandboxRepository(spec)
    canonical = _RecordingFinancialRepository()

    with pytest.raises(FinancialValidationError, match="formula must not be blank"):
        repo.promote_validated_spec_to_financial_cells(spec.id, canonical)

    assert canonical.upserts == []
    assert repo.promoted_payload is None


def test_sandbox_promotion_rejects_project_mismatch_before_validation() -> None:
    spec = _validated_spec(
        spec_json={
            "compiled_cells": [
                {
                    **_valid_cell("wrong-project"),
                    "formula": "",
                }
            ]
        }
    )
    repo = _SandboxRepository(spec)
    canonical = _RecordingFinancialRepository()

    with pytest.raises(ValueError, match="project_id does not match"):
        repo.promote_validated_spec_to_financial_cells(spec.id, canonical)

    assert canonical.upserts == []
    assert repo.promoted_payload is None


def test_sandbox_promotion_uses_explicit_compiled_cells_override() -> None:
    spec = _validated_spec(spec_json={"compiled_cells": []})
    repo = _SandboxRepository(spec)
    canonical = _RecordingFinancialRepository()

    result = repo.promote_validated_spec_to_financial_cells(
        spec.id,
        canonical,
        compiled_cells=[_valid_cell(spec.project_id, cell_ref="EBITDA")],
    )

    assert result.cell_refs == ("EBITDA",)
    assert result.promoted_to["cell_count"] == 1
    assert repo.row is not None
    assert repo.row.status == "promoted"
    assert repo.row.promoted_to == result.promoted_to
    assert len(canonical.upserts) == 1
    assert canonical.upserts[0]["promoted_from_spec"] == spec.id
    assert canonical.upserts[0]["thesis_pillar_id"] == spec.thesis_pillar_id
