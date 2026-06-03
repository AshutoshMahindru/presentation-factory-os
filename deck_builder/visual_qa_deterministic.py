from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeterministicVisualQAResult:
    status: str
    score: float
    metrics: dict[str, float]
    findings: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.status == "passed"


class DeterministicVisualQA:
    """Local visual checks that require no browser, image library, or model."""

    def score_slide(self, slide: dict[str, Any]) -> DeterministicVisualQAResult:
        content = slide.get("content", {}) or {}
        headline = str(content.get("headline") or slide.get("headline") or "")
        body = str(content.get("body") or slide.get("body") or "")
        visual_quality = str(slide.get("visual_quality") or "unknown")

        findings: list[str] = []
        headline_chars = len(headline)
        body_words = len(body.split())
        text_load = headline_chars + body_words * 7
        evidence_refs = len(content.get("evidence_refs", []) or [])

        if headline_chars == 0:
            findings.append("missing_headline")
        if headline_chars > 95:
            findings.append("headline_too_long")
        if body_words > 90:
            findings.append("body_too_dense")
        if visual_quality == "degraded":
            findings.append("degraded_visual")
        if slide.get("materiality") in {"high", "medium"} and evidence_refs == 0:
            findings.append("missing_material_evidence")

        penalty = 0.0
        penalty += max(0, headline_chars - 72) / 72
        penalty += max(0, body_words - 55) / 55
        penalty += 0.35 if visual_quality == "degraded" else 0.0
        penalty += 0.25 if "missing_material_evidence" in findings else 0.0
        score = max(0.0, round(1.0 - penalty, 3))
        status = "passed" if score >= 0.72 and not {"missing_headline", "degraded_visual"} & set(findings) else "failed"

        return DeterministicVisualQAResult(
            status=status,
            score=score,
            metrics={
                "headline_chars": float(headline_chars),
                "body_words": float(body_words),
                "text_load": float(text_load),
                "evidence_refs": float(evidence_refs),
            },
            findings=tuple(findings),
        )

    def score_deck(self, deck: dict[str, Any]) -> DeterministicVisualQAResult:
        slide_results = [self.score_slide(slide) for slide in deck.get("slides", []) or []]
        if not slide_results:
            return DeterministicVisualQAResult("failed", 0.0, {"slide_count": 0.0}, ("missing_slides",))

        score = round(sum(result.score for result in slide_results) / len(slide_results), 3)
        findings = tuple(
            f"slide_{index}:{finding}"
            for index, result in enumerate(slide_results, start=1)
            for finding in result.findings
        )
        status = "passed" if all(result.passed for result in slide_results) else "failed"
        return DeterministicVisualQAResult(
            status=status,
            score=score,
            metrics={"slide_count": float(len(slide_results))},
            findings=findings,
        )
