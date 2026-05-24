from __future__ import annotations

from dataclasses import dataclass


QueryClass = str


@dataclass(frozen=True)
class QueryClassification:
    query_classification: QueryClass
    confidence: float
    reason: str


class QueryClassifier:
    FINANCIAL_TERMS = {
        "financial",
        "revenue",
        "margin",
        "ebitda",
        "irr",
        "payback",
        "unit economics",
        "contribution",
        "cash flow",
        "valuation",
        "model",
        "scenario",
    }

    STRATEGIC_TERMS = {
        "strategy",
        "market",
        "competitive",
        "competitor",
        "risk",
        "thesis",
        "positioning",
        "tam",
        "sam",
        "som",
        "contradiction",
        "claim",
        "source",
        "evidence",
    }

    NARRATIVE_TERMS = {
        "story",
        "narrative",
        "slide sequence",
        "arc",
        "objection",
        "preemption",
        "ask",
        "decision",
        "flow",
    }

    VISUAL_TERMS = {
        "visual",
        "chart",
        "diagram",
        "layout",
        "screenshot",
        "design",
        "density",
        "legibility",
        "render",
    }

    def classify(self, query: str) -> QueryClassification:
        normalized = query.lower().strip()

        scores = {
            "financial": self._score(normalized, self.FINANCIAL_TERMS),
            "strategic": self._score(normalized, self.STRATEGIC_TERMS),
            "narrative": self._score(normalized, self.NARRATIVE_TERMS),
            "visual": self._score(normalized, self.VISUAL_TERMS),
        }

        best_class, best_score = max(scores.items(), key=lambda item: item[1])

        if best_score == 0:
            return QueryClassification(
                query_classification="unknown",
                confidence=0.35,
                reason="No known routing terms matched.",
            )

        confidence = min(0.95, 0.55 + (best_score * 0.10))
        return QueryClassification(
            query_classification=best_class,
            confidence=confidence,
            reason=f"Matched {best_score} routing term(s) for {best_class}.",
        )

    def _score(self, query: str, terms: set[str]) -> int:
        return sum(1 for term in terms if term in query)
