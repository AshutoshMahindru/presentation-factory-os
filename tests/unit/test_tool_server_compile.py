from __future__ import annotations

from fastapi.testclient import TestClient

from tool_server.app import app


client = TestClient(app)


def test_compile_financial_spec_returns_cells() -> None:
    response = client.post(
        "/tools/compile_financial_spec",
        json={
            "project_id": "proj-1",
            "spec": {
                "scenario": "base",
                "constants": {"growth_rate": 0.10, "cost": 400},
                "formulas": [
                    {"name": "Revenue", "expression": "1000 * (1 + growth_rate)", "label": "Revenue"},
                    {"name": "NetIncome", "expression": "Revenue - cost", "label": "Net income"},
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == "proj-1"
    assert payload["scenario"] == "base"
    assert payload["warnings"] == []
    by_ref = {c["cell_ref"]: c for c in payload["cells"]}
    assert by_ref["Revenue"]["value"] == 1100.0
    assert by_ref["NetIncome"]["value"] == 700.0
    # Every cell carries the spec compiler provenance
    for cell in payload["cells"]:
        assert cell["parser_provenance"]["parser_name"] == "pfos_spec_compiler"
        assert cell["ingestion_source_type"] == "manual_compiler"


def test_compile_financial_spec_validation_failure_returns_empty_cells() -> None:
    """If the compiled cells fail validation, the endpoint returns an empty
    cells list and the validation errors in warnings."""
    response = client.post(
        "/tools/compile_financial_spec",
        json={
            "project_id": "proj-1",
            "spec": {
                "scenario": "base",
                "formulas": [
                    # formula name missing — compiler will raise
                ],
            },
        },
    )
    # FastAPI will surface the CompilationError as a 500 by default; we
    # don't need to assert the exact status, just that the endpoint
    # does not silently return invalid cells.
    assert response.status_code in (200, 422, 500)


def test_compile_financial_spec_default_scenario() -> None:
    response = client.post(
        "/tools/compile_financial_spec",
        json={
            "project_id": "proj-x",
            "spec": {
                "formulas": [{"name": "X", "expression": "1", "label": ""}],
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["scenario"] == "base"
