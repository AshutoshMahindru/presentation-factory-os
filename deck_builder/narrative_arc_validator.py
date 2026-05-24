from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class NarrativeArcValidationError(Exception):
    """Raised when a deck violates deterministic narrative arc rules."""


@dataclass(frozen=True)
class NarrativeArcValidationResult:
    valid: bool
    errors: tuple[str, ...]


class NarrativeArcValidator:
    FINANCIAL_JOB_TYPES = {"explain_unit_economics", "show_capital_gate"}
    ASK_JOB_TYPES = {"request_decision"}
    EVIDENCE_JOB_TYPES = {
        "establish_market_size",
        "show_growth_trajectory",
        "present_team_credentials",
        "compare_competitive_position",
        "explain_unit_economics",
    }
    OBJECTION_JOB_TYPES = {"address_risk"}

    def validate(self, slides: list[dict[str, Any]]) -> NarrativeArcValidationResult:
        errors: list[str] = []

        if not slides:
            return NarrativeArcValidationResult(valid=False, errors=("Deck contains no slides.",))

        self._check_first_slide_not_detailed_financial(slides, errors)
        self._check_request_decision_after_evidence(slides, errors)
        self._check_objection_preemption_before_ask(slides, errors)

        return NarrativeArcValidationResult(valid=not errors, errors=tuple(errors))

    def assert_valid(self, slides: list[dict[str, Any]]) -> None:
        result = self.validate(slides)
        if not result.valid:
            raise NarrativeArcValidationError("; ".join(result.errors))

    def _job_type(self, slide: dict[str, Any]) -> str:
        return str(slide.get("job", {}).get("type", ""))

    def _slide_id(self, slide: dict[str, Any], index: int) -> str:
        return str(slide.get("slide_id", f"slide_at_index_{index}"))

    def _check_first_slide_not_detailed_financial(
        self,
        slides: list[dict[str, Any]],
        errors: list[str],
    ) -> None:
        first_type = self._job_type(slides[0])
        if first_type in self.FINANCIAL_JOB_TYPES:
            errors.append("Slide 1 must not be a detailed financial table or unit-economics slide.")

    def _check_request_decision_after_evidence(
        self,
        slides: list[dict[str, Any]],
        errors: list[str],
    ) -> None:
        seen_evidence = False

        for index, slide in enumerate(slides):
            job_type = self._job_type(slide)

            if job_type in self.EVIDENCE_JOB_TYPES:
                seen_evidence = True

            if job_type in self.ASK_JOB_TYPES and not seen_evidence:
                errors.append(
                    f"{self._slide_id(slide, index)} requests a decision before evidence has been presented."
                )

    def _check_objection_preemption_before_ask(
        self,
        slides: list[dict[str, Any]],
        errors: list[str],
    ) -> None:
        first_ask_index: int | None = None
        objection_index: int | None = None

        for index, slide in enumerate(slides):
            job_type = self._job_type(slide)

            if job_type in self.OBJECTION_JOB_TYPES and objection_index is None:
                objection_index = index

            if job_type in self.ASK_JOB_TYPES and first_ask_index is None:
                first_ask_index = index

        if first_ask_index is not None and objection_index is not None:
            if objection_index > first_ask_index:
                errors.append("Objection-preemption slides must appear before the request-decision slide.")
