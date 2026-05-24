import pytest

from deck_builder.narrative_arc_validator import (
    NarrativeArcValidationError,
    NarrativeArcValidator,
)


def slide(slide_id: str, job_type: str):
    return {
        "slide_id": slide_id,
        "job": {
            "type": job_type,
            "required_evidence": ["source_001"],
        },
        "content": {
            "headline": "Headline",
            "body": "Body",
            "chart_id": None,
            "evidence_refs": ["source_001"],
        },
        "visual_quality": "code_generated",
        "materiality": "high",
    }


def valid_deck():
    return [
        slide("slide_001", "establish_market_size"),
        slide("slide_002", "show_growth_trajectory"),
        slide("slide_003", "address_risk"),
        slide("slide_004", "request_decision"),
    ]


def test_valid_narrative_arc_passes():
    validator = NarrativeArcValidator()
    result = validator.validate(valid_deck())
    assert result.valid is True
    assert result.errors == ()


def test_empty_deck_fails():
    validator = NarrativeArcValidator()
    result = validator.validate([])
    assert result.valid is False
    assert "Deck contains no slides." in result.errors


def test_slide_one_must_not_be_detailed_financial():
    validator = NarrativeArcValidator()
    deck = valid_deck()
    deck[0] = slide("slide_001", "explain_unit_economics")

    result = validator.validate(deck)

    assert result.valid is False
    assert any("Slide 1" in error for error in result.errors)


def test_request_decision_cannot_come_before_evidence():
    validator = NarrativeArcValidator()
    deck = [
        slide("slide_001", "request_decision"),
        slide("slide_002", "establish_market_size"),
    ]

    with pytest.raises(NarrativeArcValidationError):
        validator.assert_valid(deck)


def test_objection_preemption_must_come_before_ask():
    validator = NarrativeArcValidator()
    deck = [
        slide("slide_001", "establish_market_size"),
        slide("slide_002", "request_decision"),
        slide("slide_003", "address_risk"),
    ]

    result = validator.validate(deck)

    assert result.valid is False
    assert any("Objection-preemption" in error for error in result.errors)
