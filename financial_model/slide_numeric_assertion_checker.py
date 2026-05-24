from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


class NumericAssertionValidationError(Exception):
    """Raised when a slide contains numeric assertions without financial references."""


@dataclass(frozen=True)
class NumericAssertionResult:
    valid: bool
    has_numeric_assertions: bool
    financial_refs: tuple[str, ...]
    numeric_matches: tuple[str, ...]
    errors: tuple[str, ...]


class SlideNumericAssertionChecker:
    """
    Detects numeric assertions in slide body copy and requires financial_refs.

    This is intentionally conservative:
    - percentages: 38%, 12.5%
    - currency-like values: $1.2m, ₹4 crore, INR 50 lakh
    - plain numeric business assertions: 200 orders/day, 3.5x, 18 months
    """

    NUMERIC_PATTERN = re.compile(
        r"""
        (?:
            (?:[$₹€£]\s?\d+(?:\.\d+)?\s?(?:k|m|bn|cr|crore|lakh)?) |
            (?:\b(?:INR|USD|EUR|GBP)\s?\d+(?:\.\d+)?\s?(?:k|m|bn|cr|crore|lakh)?) |
            (?:\b\d+(?:\.\d+)?\s?%) |
            (?:\b\d+(?:\.\d+)?x\b) |
            (?:\b\d+(?:\.\d+)?\s?(?:orders/day|orders|months|years|days|stores|locations|customers|units)\b) |
            (?:\b(?:month|year|day|week|quarter)\s?\d+(?:\.\d+)?\b)
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    def check_slide(self, slide: dict[str, Any]) -> NumericAssertionResult:
        content = slide.get("content", {}) or {}
        body = str(content.get("body", "") or "")
        financial_refs = tuple(content.get("financial_refs", []) or [])

        matches = tuple(match.group(0).strip() for match in self.NUMERIC_PATTERN.finditer(body))
        has_numeric_assertions = bool(matches)

        errors: list[str] = []
        if has_numeric_assertions and not financial_refs:
            errors.append("Slide body contains numeric assertions but content.financial_refs is empty.")

        return NumericAssertionResult(
            valid=not errors,
            has_numeric_assertions=has_numeric_assertions,
            financial_refs=financial_refs,
            numeric_matches=matches,
            errors=tuple(errors),
        )

    def assert_valid(self, slide: dict[str, Any]) -> None:
        result = self.check_slide(slide)
        if not result.valid:
            raise NumericAssertionValidationError("; ".join(result.errors))
