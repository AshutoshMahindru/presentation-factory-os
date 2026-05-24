import pytest

from deck_builder.slide_schema_validator import (
    SlideSchemaValidationError,
    SlideSchemaValidator,
)


def valid_slide_payload():
    return {
        "slide_id": "slide_001",
        "job": {
            "type": "establish_market_size",
            "required_evidence": ["source_001"],
            "objective": "Show the size of the market opportunity",
            "phase": "narrative",
        },
        "content": {
            "headline": "The market is large enough to support venture-scale growth",
            "body": "The addressable market is attractive and evidence-backed.",
            "chart_id": None,
            "evidence_refs": ["source_001"],
            "financial_refs": [],
        },
        "visual_quality": "code_generated",
        "materiality": "high",
        "narrative_arc": "problem_solution",
    }


def test_valid_slide_payload_passes():
    validator = SlideSchemaValidator.from_file()
    result = validator.validate(valid_slide_payload())
    assert result.valid is True
    assert result.errors == ()


def test_missing_materiality_fails():
    validator = SlideSchemaValidator.from_file()
    payload = valid_slide_payload()
    payload.pop("materiality")

    result = validator.validate(payload)

    assert result.valid is False
    assert any("materiality" in error for error in result.errors)


def test_invalid_job_type_fails():
    validator = SlideSchemaValidator.from_file()
    payload = valid_slide_payload()
    payload["job"]["type"] = "made_up_job"

    with pytest.raises(SlideSchemaValidationError):
        validator.assert_valid(payload)


def test_required_evidence_must_not_be_empty():
    validator = SlideSchemaValidator.from_file()
    payload = valid_slide_payload()
    payload["job"]["required_evidence"] = []

    result = validator.validate(payload)

    assert result.valid is False
    assert any("required_evidence" in error for error in result.errors)


def test_headline_max_length_enforced():
    validator = SlideSchemaValidator.from_file()
    payload = valid_slide_payload()
    payload["content"]["headline"] = "x" * 121

    result = validator.validate(payload)

    assert result.valid is False
    assert any("headline" in error for error in result.errors)


def test_invalid_visual_quality_fails():
    validator = SlideSchemaValidator.from_file()
    payload = valid_slide_payload()
    payload["visual_quality"] = "hand_drawn"

    result = validator.validate(payload)

    assert result.valid is False
    assert any("visual_quality" in error for error in result.errors)


def test_invalid_narrative_arc_fails():
    validator = SlideSchemaValidator.from_file()
    payload = valid_slide_payload()
    payload["narrative_arc"] = "random_arc"

    result = validator.validate(payload)

    assert result.valid is False
    assert any("narrative_arc" in error for error in result.errors)
