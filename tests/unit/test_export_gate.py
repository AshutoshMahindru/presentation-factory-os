import pytest

from deck_builder.export_gate import ExportGate, ExportGateError


def valid_slide(slide_id="slide_001"):
    return {
        "slide_id": slide_id,
        "visual_quality": "code_generated",
        "materiality": "high",
        "content": {
            "headline": "Headline",
            "body": "Evidence-backed body.",
            "chart_id": None,
            "evidence_refs": ["source_001"],
            "financial_refs": [],
        },
    }


def valid_deck():
    return {
        "slides": [valid_slide()],
        "financial_validation_status": "validated",
        "unsupported_financial_claim_count": 0,
        "financial_cells": {},
        "sensitive_data_detected": False,
        "pii_exposure_detected": False,
        "artifacts": [],
        "pending_source_retraction_count": 0,
        "unprocessed_outbox_count": 0,
    }


def test_valid_deck_can_export():
    result = ExportGate().evaluate(valid_deck())
    assert result.export_allowed is True
    assert result.blocking_reasons == ()


def test_degraded_high_materiality_visual_blocks_export():
    deck = valid_deck()
    deck["slides"][0]["visual_quality"] = "degraded"
    deck["slides"][0]["materiality"] = "high"

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is False
    assert any("degraded visuals" in reason for reason in result.blocking_reasons)


def test_degraded_medium_materiality_visual_blocks_export():
    deck = valid_deck()
    deck["slides"][0]["visual_quality"] = "degraded"
    deck["slides"][0]["materiality"] = "medium"

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is False
    assert any("degraded visuals" in reason for reason in result.blocking_reasons)


def test_degraded_low_materiality_visual_warns_but_does_not_block():
    deck = valid_deck()
    deck["slides"][0]["visual_quality"] = "degraded"
    deck["slides"][0]["materiality"] = "low"

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is True
    assert result.warnings


def test_unvalidated_financials_block_export():
    deck = valid_deck()
    deck["financial_validation_status"] = "failed"

    with pytest.raises(ExportGateError):
        ExportGate().assert_export_allowed(deck)


def test_unsupported_financial_claims_block_export():
    deck = valid_deck()
    deck["unsupported_financial_claim_count"] = 1

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is False
    assert any("Unsupported financial claims" in reason for reason in result.blocking_reasons)


def test_numeric_assertion_without_financial_refs_blocks_export():
    deck = valid_deck()
    deck["slides"][0]["content"]["body"] = "Contribution margin improves to 38% by month 18."

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is False
    assert any("numeric assertions" in reason for reason in result.blocking_reasons)


def test_financial_ref_missing_financial_cell_blocks_export():
    deck = valid_deck()
    deck["slides"][0]["content"]["body"] = "Contribution margin improves to 38% by month 18."
    deck["slides"][0]["content"]["financial_refs"] = ["FM!CM_M18_BASE"]

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is False
    assert any("does not map to a financial cell" in reason for reason in result.blocking_reasons)


def test_financial_ref_must_map_to_validated_financial_cell():
    deck = valid_deck()
    deck["slides"][0]["content"]["body"] = "Contribution margin improves to 38% by month 18."
    deck["slides"][0]["content"]["financial_refs"] = ["FM!CM_M18_BASE"]
    deck["financial_cells"] = {
        "FM!CM_M18_BASE": {
            "cell_ref": "FM!CM_M18_BASE",
            "validation_status": "failed",
        }
    }

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is False
    assert any("is not validated" in reason for reason in result.blocking_reasons)


def test_validated_financial_ref_allows_financial_assertion():
    deck = valid_deck()
    deck["slides"][0]["content"]["body"] = "Contribution margin improves to 38% by month 18."
    deck["slides"][0]["content"]["financial_refs"] = ["FM!CM_M18_BASE"]
    deck["financial_cells"] = {
        "FM!CM_M18_BASE": {
            "cell_ref": "FM!CM_M18_BASE",
            "validation_status": "validated",
        }
    }

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is True


def test_missing_source_attribution_blocks_material_slide():
    deck = valid_deck()
    deck["slides"][0]["content"]["evidence_refs"] = []

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is False
    assert any("active sources" in reason for reason in result.blocking_reasons)


def test_sensitive_data_blocks_export():
    deck = valid_deck()
    deck["sensitive_data_detected"] = True

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is False
    assert any("Sensitive data" in reason for reason in result.blocking_reasons)


def test_pii_exposure_blocks_export():
    deck = valid_deck()
    deck["pii_exposure_detected"] = True

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is False
    assert any("Sensitive data" in reason for reason in result.blocking_reasons)


def test_stale_artifact_blocks_export():
    deck = valid_deck()
    deck["artifacts"] = [{"id": "slide_draft_001", "status": "stale_due_to_retreat"}]

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is False
    assert any("stale_due_to_retreat" in reason for reason in result.blocking_reasons)


def test_pending_source_retraction_cascade_blocks_export():
    deck = valid_deck()
    deck["pending_source_retraction_count"] = 1

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is False
    assert any("source retraction cascade" in reason for reason in result.blocking_reasons)


def test_pending_outbox_blocks_export():
    deck = valid_deck()
    deck["unprocessed_outbox_count"] = 1

    result = ExportGate().evaluate(deck)

    assert result.export_allowed is False
    assert any("side effects" in reason for reason in result.blocking_reasons)
