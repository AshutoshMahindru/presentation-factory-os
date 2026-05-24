from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from retrieval_engine.classifiers import QueryClassification, QueryClassifier


@dataclass(frozen=True)
class RoutingDecision:
    mode: str
    query_classification: str
    confidence: float
    forced_hybrid: bool
    escalation_reason: str | None
    recommended_next_action: str


class RetrievalRouter:
    def __init__(self, classifier: QueryClassifier | None = None) -> None:
        self.classifier = classifier or QueryClassifier()

    def route(self, query: str, mode_hint: str | None = None) -> RoutingDecision:
        classification = self.classifier.classify(query)

        if mode_hint:
            return RoutingDecision(
                mode=mode_hint,
                query_classification=classification.query_classification,
                confidence=classification.confidence,
                forced_hybrid=mode_hint == "hybrid",
                escalation_reason="Mode hint supplied by caller.",
                recommended_next_action="Use caller-specified retrieval mode.",
            )

        return self._route_from_classification(classification)

    def _route_from_classification(self, classification: QueryClassification) -> RoutingDecision:
        query_class = classification.query_classification

        if query_class == "financial":
            return RoutingDecision(
                mode="structured",
                query_classification=query_class,
                confidence=classification.confidence,
                forced_hybrid=False,
                escalation_reason=None,
                recommended_next_action="Query financial_cells and structured financial validation outputs.",
            )

        if query_class == "strategic":
            return RoutingDecision(
                mode="hybrid",
                query_classification=query_class,
                confidence=classification.confidence,
                forced_hybrid=True,
                escalation_reason="Strategic queries require semantic context plus evidence graph validation.",
                recommended_next_action="Use semantic retrieval and graph evidence checks.",
            )

        if query_class == "narrative":
            return RoutingDecision(
                mode="semantic",
                query_classification=query_class,
                confidence=classification.confidence,
                forced_hybrid=False,
                escalation_reason=None,
                recommended_next_action="Retrieve narrative notes, slide jobs, and objection map context.",
            )

        if query_class == "visual":
            return RoutingDecision(
                mode="semantic",
                query_classification=query_class,
                confidence=classification.confidence,
                forced_hybrid=False,
                escalation_reason=None,
                recommended_next_action="Retrieve slide, layout, chart, and design-token context.",
            )

        return RoutingDecision(
            mode="hybrid",
            query_classification="unknown",
            confidence=classification.confidence,
            forced_hybrid=True,
            escalation_reason="Low-confidence unknown query requires broad retrieval and gap reporting.",
            recommended_next_action="Ask for a more specific query or run hybrid retrieval with gaps.",
        )

    def build_empty_payload(self, query: str, project_id: str | None = None) -> dict:
        decision = self.route(query)
        request_id = str(uuid4())

        gaps = []
        if decision.query_classification == "unknown":
            gaps.append(
                {
                    "gap_type": "scope_mismatch",
                    "description": "Query could not be confidently classified.",
                    "severity": "warning",
                }
            )

        return {
            "request_id": request_id,
            "query": query,
            "routing_decision": {
                "mode": decision.mode,
                "validation_metadata": {
                    "query_classification": decision.query_classification,
                    "forced_hybrid": decision.forced_hybrid,
                    "escalation_reason": decision.escalation_reason,
                },
            },
            "items": [],
            "provenance": {
                "retrieved_at": "2026-05-24T00:00:00Z",
                "retrieval_engine_version": "3.2.4",
                "stores_queried": [],
                "trace_id": request_id,
            },
            "confidence": decision.confidence,
            "gaps": gaps,
            "recommended_next_action": decision.recommended_next_action,
        }
