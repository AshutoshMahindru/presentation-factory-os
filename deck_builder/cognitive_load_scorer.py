from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CognitiveLoadScore:
    score: float
    band: str
    findings: tuple[str, ...]


class CognitiveLoadScorer:
    def score_slide(self, slide: dict[str, Any]) -> CognitiveLoadScore:
        content = slide.get("content", {}) or {}
        headline = str(content.get("headline") or slide.get("headline") or "")
        body = str(content.get("body") or slide.get("body") or "")
        bullets = content.get("bullets", []) or []
        chart_count = len(content.get("charts", []) or ([] if not content.get("chart_id") else [content.get("chart_id")]))

        load = len(headline) / 80 + len(body.split()) / 65 + len(bullets) / 7 + chart_count / 3
        findings: list[str] = []
        if len(headline) > 90:
            findings.append("headline_too_long")
        if len(body.split()) > 80:
            findings.append("body_too_dense")
        if len(bullets) > 6:
            findings.append("too_many_bullets")
        if chart_count > 2:
            findings.append("too_many_visual_objects")

        score = round(min(1.0, load), 3)
        if score < 0.45:
            band = "low"
        elif score < 0.75:
            band = "moderate"
        else:
            band = "high"
        return CognitiveLoadScore(score=score, band=band, findings=tuple(findings))
