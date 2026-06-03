from __future__ import annotations

from system.guards import GuardEvaluator


def valid_cell(**overrides):
    cell = {
        "project_id": "project-1",
        "scenario": "base",
        "cell_ref": "Revenue",
        "label": "Revenue",
        "value": 100,
        "formula": "50+50",
        "artifact_status": "active",
    }
    cell.update(overrides)
    return cell


def test_model_validated_guard_validates_financial_cells_when_present() -> None:
    result = GuardEvaluator(audience_validator=object()).evaluate(
        "model_validated",
        {"financial_cells": [valid_cell()]},
    )

    assert result.passed is True


def test_model_validated_guard_rejects_stale_cells_even_when_context_guard_is_true() -> None:
    result = GuardEvaluator(audience_validator=object()).evaluate(
        "model_validated",
        {
            "guards": {"model_validated": True},
            "financial_cells": [valid_cell(artifact_status="stale_due_to_retreat")],
        },
    )

    assert result.passed is False
    assert "non-active cells" in str(result.reason)
    assert "stale_due_to_retreat" in str(result.reason)


def test_model_validated_guard_preserves_context_fallback_when_cells_absent() -> None:
    result = GuardEvaluator(audience_validator=object()).evaluate(
        "model_validated",
        {"guards": {"model_validated": True}},
    )

    assert result.passed is True


def test_model_validated_guard_fails_closed_without_cells_or_context_flag() -> None:
    result = GuardEvaluator(audience_validator=object()).evaluate(
        "model_validated",
        {"guards": {}},
    )

    assert result.passed is False
    assert "financial_cells are required" in str(result.reason)
