from __future__ import annotations

import pytest

from deck_builder.chat_presentation import create_presentation_from_chat
from deck_builder.slide_schema_validator import SlideSchemaValidator


def test_chat_message_creates_validated_web_presentation_preview() -> None:
    run = create_presentation_from_chat(
        "Create a 5 slide board deck for PFOS automation reliability.",
        {
            "source_refs": ["source_reliability", "source_market"],
            "decision_required": "Approve the reliability roadmap.",
        },
    )

    payload = run.to_payload()

    assert payload["brief"]["audience"] == "board"
    assert payload["brief"]["slide_count"] == 5
    assert payload["web_preview"]["mime_type"] == "text/html"
    assert payload["web_preview"]["slide_count"] == len(payload["slides"])
    assert payload["export_gate"]["export_allowed"] is True
    assert payload["evidence_gaps"] == []
    assert payload["export_metadata"]["metadata_type"] == "multi_format_export"

    validator = SlideSchemaValidator.from_file()
    for slide in payload["slides"]:
        validator.assert_valid(slide)


def test_chat_message_without_external_sources_surfaces_evidence_gaps_but_renders_preview() -> None:
    run = create_presentation_from_chat(
        "Make an investor deck about PFOS market expansion.",
        {"decision_required": "Open investor diligence."},
    )
    payload = run.to_payload()

    assert payload["brief"]["audience"] == "investor"
    assert payload["export_gate"]["export_allowed"] is True
    assert any("external source refs" in gap for gap in payload["evidence_gaps"])
    assert any("operator chat prompt" in gap for gap in payload["evidence_gaps"])
    assert payload["recommended_next_action"] == (
        "Review the preview, attach external sources, then regenerate for evidence-backed export."
    )
    assert "operator_brief_" in payload["slides"][0]["content"]["evidence_refs"][0]


def test_empty_chat_message_is_rejected() -> None:
    with pytest.raises(ValueError, match="chat message is required"):
        create_presentation_from_chat("   ")
