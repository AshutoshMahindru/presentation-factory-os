from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from financial_model.spec_compiler import FinancialSpecCompiler
from system.financial_spec_repository import (
    FinancialSpecRepository,
    FinancialSpecRow,
)
from tool_server.app import app


class _InMemoryFinancialSpecRepository(FinancialSpecRepository):
    def __init__(self, row: FinancialSpecRow) -> None:
        self.row = row
        self.promoted_payload: dict[str, Any] | None = None

    def get_spec(self, spec_id):  # type: ignore[no-untyped-def]
        return self.row if spec_id == self.row.id else None

    def mark_promoted(self, spec_id, promoted_to):  # type: ignore[no-untyped-def]
        assert spec_id == self.row.id
        self.promoted_payload = promoted_to
        self.row = replace(self.row, status="promoted", promoted_to=promoted_to)


class _RecordingFinancialRepository:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

    def upsert_cell(self, **kwargs: Any) -> object:
        self.upserts.append(kwargs)
        return object()


def _spec_row(
    *,
    project_id,
    thesis_pillar_id,
    spec_json: dict[str, Any],
    status: str = "validated",
) -> FinancialSpecRow:
    return FinancialSpecRow(
        id=uuid4(),
        project_id=project_id,
        thesis_pillar_id=thesis_pillar_id,
        name="Sandbox revenue model",
        spec_json=spec_json,
        status=status,
        validation_errors=[],
        promoted_to=None,
        created_at="2026-06-03T00:00:00Z",
        updated_at="2026-06-03T00:00:00Z",
    )


def test_sandbox_spec_compiles_and_promotes_with_lineage() -> None:
    project_id = uuid4()
    pillar_id = uuid4()
    source_spec = {
        "scenario": "base",
        "constants": {"growth_rate": 0.12, "opex": 420},
        "formulas": [
            {
                "name": "Revenue",
                "expression": "1000 * (1 + growth_rate)",
                "label": "Revenue",
            },
            {
                "name": "EBITDA",
                "expression": "Revenue - opex",
                "label": "EBITDA",
            },
        ],
    }

    compiled = FinancialSpecCompiler().compile(
        source_spec,
        project_id=str(project_id),
    )
    compiled_cells = [cell.to_validator_dict() for cell in compiled.cells]
    spec_json = {
        **source_spec,
        "compiled_cells": compiled_cells,
        "compiler_warnings": list(compiled.warnings),
    }
    spec = _spec_row(
        project_id=project_id,
        thesis_pillar_id=pillar_id,
        spec_json=spec_json,
    )
    sandbox_repo = _InMemoryFinancialSpecRepository(spec)
    canonical_repo = _RecordingFinancialRepository()

    promotion = sandbox_repo.promote_validated_spec_to_financial_cells(
        spec.id,
        canonical_repo,
    )

    assert promotion.cell_refs == ("Revenue", "EBITDA")
    assert promotion.promoted_to == {
        "canonical_table": "financial_cells",
        "cell_count": 2,
        "cell_refs": ["Revenue", "EBITDA"],
        "scenarios": ["base"],
    }
    assert sandbox_repo.row.status == "promoted"
    assert sandbox_repo.promoted_payload == promotion.promoted_to

    assert len(canonical_repo.upserts) == 2
    revenue, ebitda = canonical_repo.upserts
    assert revenue["project_id"] == project_id
    assert revenue["thesis_pillar_id"] == pillar_id
    assert revenue["promoted_from_spec"] == spec.id
    assert revenue["scenario"] == "base"
    assert revenue["cell_ref"] == "Revenue"
    assert revenue["value"] == pytest.approx(1120.0)
    assert revenue["ingestion_source_type"] == "manual_compiler"
    assert revenue["parser_provenance"]["parser_name"] == "pfos_spec_compiler"
    assert ebitda["cell_ref"] == "EBITDA"
    assert ebitda["value"] == pytest.approx(700.0)


def test_sandbox_promotion_requires_validated_spec() -> None:
    project_id = uuid4()
    spec = _spec_row(
        project_id=project_id,
        thesis_pillar_id=None,
        spec_json={
            "compiled_cells": [
                {
                    "project_id": str(project_id),
                    "scenario": "base",
                    "cell_ref": "Revenue",
                    "label": "Revenue",
                    "value": 1,
                    "formula": "1",
                }
            ]
        },
        status="compiled",
    )

    with pytest.raises(ValueError, match="must be validated before promotion"):
        _InMemoryFinancialSpecRepository(spec).promote_validated_spec_to_financial_cells(
            spec.id,
            _RecordingFinancialRepository(),
        )


def test_compile_financial_spec_api_returns_422_for_compilation_errors() -> None:
    client = TestClient(app)

    response = client.post(
        "/tools/compile_financial_spec",
        json={
            "project_id": str(uuid4()),
            "spec": {
                "scenario": "base",
                "formulas": [
                    {
                        "name": "Revenue",
                        "expression": "unknown_input + 1",
                        "label": "Revenue",
                    }
                ],
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "financial_spec_compilation_failed"
    assert "unknown references" in response.json()["detail"]["message"]
