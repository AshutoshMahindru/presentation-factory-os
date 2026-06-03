from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deck_builder.cognitive_load_scorer import CognitiveLoadScorer


@dataclass(frozen=True)
class SlideMasterDecision:
    master: str
    layout: str
    cognitive_load_band: str
    findings: tuple[str, ...]


class SlideMasterEngine:
    def __init__(self, scorer: CognitiveLoadScorer | None = None) -> None:
        self.scorer = scorer or CognitiveLoadScorer()

    def assign(self, slide: dict[str, Any]) -> SlideMasterDecision:
        content = slide.get("content", {}) or {}
        has_chart = bool(content.get("chart_id") or content.get("charts"))
        has_table = bool(content.get("table_id") or content.get("tables"))
        materiality = slide.get("materiality") or "medium"
        load = self.scorer.score_slide(slide)

        if has_chart and has_table:
            layout = "evidence-grid"
        elif has_chart:
            layout = "chart-led"
        elif has_table:
            layout = "table-led"
        else:
            layout = "headline-body"

        master = "executive-evidence" if materiality in {"high", "medium"} else "appendix-light"
        findings = load.findings
        if load.band == "high":
            findings = (*findings, "requires_simplification")

        return SlideMasterDecision(
            master=master,
            layout=layout,
            cognitive_load_band=load.band,
            findings=findings,
        )

    def apply(self, deck: dict[str, Any]) -> dict[str, Any]:
        slides = []
        for slide in deck.get("slides", []) or []:
            decision = self.assign(slide)
            updated = dict(slide)
            updated["slide_master"] = decision.master
            updated["layout"] = decision.layout
            updated["cognitive_load_band"] = decision.cognitive_load_band
            updated["master_findings"] = list(decision.findings)
            slides.append(updated)
        return {**deck, "slides": slides}
