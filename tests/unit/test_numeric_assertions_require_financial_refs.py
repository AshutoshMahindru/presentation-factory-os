import pytest

from financial_model.slide_numeric_assertion_checker import (
    NumericAssertionValidationError,
    SlideNumericAssertionChecker,
)


def slide(body: str, financial_refs=None):
    return {
        "slide_id": "slide_001",
        "content": {
            "headline": "Unit economics",
            "body": body,
            "chart_id": None,
            "evidence_refs": ["source_001"],
            "financial_refs": financial_refs or [],
        },
    }


def test_body_without_numbers_does_not_require_financial_refs():
    checker = SlideNumericAssertionChecker()
    result = checker.check_slide(slide("The model improves as density increases."))
    assert result.valid is True
    assert result.has_numeric_assertions is False


def test_percentage_requires_financial_refs():
    checker = SlideNumericAssertionChecker()
    result = checker.check_slide(slide("Contribution margin improves to 38% by month 18."))
    assert result.valid is False
    assert "38%" in result.numeric_matches
    assert "month 18" in result.numeric_matches


def test_percentage_with_financial_refs_passes():
    checker = SlideNumericAssertionChecker()
    result = checker.check_slide(
        slide(
            "Contribution margin improves to 38% by month 18.",
            financial_refs=["FM!CM_M18_BASE"],
        )
    )
    assert result.valid is True


def test_currency_requires_financial_refs():
    checker = SlideNumericAssertionChecker()
    with pytest.raises(NumericAssertionValidationError):
        checker.assert_valid(slide("The business reaches INR 50 lakh monthly revenue."))


def test_operating_metric_requires_financial_refs():
    checker = SlideNumericAssertionChecker()
    result = checker.check_slide(slide("The kitchen reaches 200 orders/day."))
    assert result.valid is False
    assert "200 orders/day" in result.numeric_matches
