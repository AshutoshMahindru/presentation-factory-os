from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from financial_model.slide_numeric_assertion_checker import SlideNumericAssertionChecker


class ExportGateError(Exception):
    """Raised when a deck cannot be exported."""


@dataclass(frozen=True)
class ExportGateResult:
    export_allowed: bool
    blocking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]


class ExportGate:
    """
    Deterministic export gate.

    This does not render a deck. It decides whether a deck is allowed to ship.
    """

    def evaluate(self, deck: dict[str, Any]) -> ExportGateResult:
        blocking: list[str] = []
        warnings: list[str] = []

        slides = deck.get("slides", []) or []

        self._check_degraded_visuals(slides, blocking, warnings)
        self._check_financial_validation(deck, slides, blocking)
        self._check_source_attribution(slides, blocking)
        self._check_sensitive_data(deck, blocking)
        self._check_stale_artifacts(deck, blocking)
        self._check_source_retraction_cascade(deck, blocking)
        self._check_outbox(deck, blocking)

        return ExportGateResult(
            export_allowed=not blocking,
            blocking_reasons=tuple(blocking),
            warnings=tuple(warnings),
        )

    def assert_export_allowed(self, deck: dict[str, Any]) -> None:
        result = self.evaluate(deck)
        if not result.export_allowed:
            raise ExportGateError("; ".join(result.blocking_reasons))

    def _check_degraded_visuals(
        self,
        slides: list[dict[str, Any]],
        blocking: list[str],
        warnings: list[str],
    ) -> None:
        for slide in slides:
            slide_id = slide.get("slide_id", "<unknown>")
            visual_quality = slide.get("visual_quality")
            materiality = slide.get("materiality")

            if visual_quality == "degraded" and materiality in {"high", "medium"}:
                blocking.append(f"{slide_id}: degraded visuals cannot ship on high/medium materiality slides.")

            if visual_quality == "degraded" and materiality == "low":
                warnings.append(f"{slide_id}: degraded visual allowed only with warning and provenance.")

    def _check_financial_validation(
        self,
        deck: dict[str, Any],
        slides: list[dict[str, Any]],
        blocking: list[str],
    ) -> None:
        if deck.get("financial_validation_status") not in {None, "validated"}:
            blocking.append("Financial calculations must pass deterministic validation.")

        unsupported_claims = int(deck.get("unsupported_financial_claim_count", 0) or 0)
        if unsupported_claims > 0:
            blocking.append("Unsupported financial claims cannot be exported.")

        checker = SlideNumericAssertionChecker()
        financial_cells = self._financial_cell_lookup(deck)
        for slide in slides:
            slide_id = slide.get("slide_id", "<unknown>")
            assertion_result = checker.check_slide(slide)

            for error in assertion_result.errors:
                blocking.append(f"{slide_id}: {error}")

            for financial_ref in assertion_result.financial_refs:
                cell = financial_cells.get(financial_ref)
                if not cell:
                    blocking.append(f"{slide_id}: financial_ref {financial_ref} does not map to a financial cell.")
                    continue

                status = cell.get("validation_status", cell.get("status"))
                if status != "validated":
                    blocking.append(f"{slide_id}: financial_ref {financial_ref} is not validated.")

    def _check_source_attribution(self, slides: list[dict[str, Any]], blocking: list[str]) -> None:
        for slide in slides:
            slide_id = slide.get("slide_id", "<unknown>")
            materiality = slide.get("materiality")
            content = slide.get("content", {}) or {}
            evidence_refs = content.get("evidence_refs", []) or []

            if materiality in {"high", "medium"} and not evidence_refs:
                blocking.append(f"{slide_id}: material claims require active sources.")

    def _check_sensitive_data(self, deck: dict[str, Any], blocking: list[str]) -> None:
        if deck.get("sensitive_data_detected") is True or deck.get("pii_exposure_detected") is True:
            blocking.append("Sensitive data requires redaction or explicit classification clearance.")

    def _check_stale_artifacts(self, deck: dict[str, Any], blocking: list[str]) -> None:
        for artifact in deck.get("artifacts", []) or []:
            artifact_id = artifact.get("id", "<unknown>")
            if artifact.get("status") == "stale_due_to_retreat":
                blocking.append(f"{artifact_id}: stale_due_to_retreat artifacts cannot be exported.")

    def _check_source_retraction_cascade(self, deck: dict[str, Any], blocking: list[str]) -> None:
        if int(deck.get("pending_source_retraction_count", 0) or 0) > 0:
            blocking.append("Pending source retraction cascade must complete before export.")

    def _check_outbox(self, deck: dict[str, Any], blocking: list[str]) -> None:
        if int(deck.get("unprocessed_outbox_count", 0) or 0) > 0:
            blocking.append("Cross-store side effects must be drained before export.")

    def _financial_cell_lookup(self, deck: dict[str, Any]) -> dict[str, dict[str, Any]]:
        cells = deck.get("financial_cells", {}) or {}
        if isinstance(cells, dict):
            return cells

        lookup: dict[str, dict[str, Any]] = {}
        for cell in cells:
            cell_ref = cell.get("cell_ref")
            if cell_ref:
                lookup[str(cell_ref)] = cell
        return lookup
