from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from retrieval_engine.classifiers import (
    QueryClassification,
    QueryClassifier,
    RetrievalQueryClassifier,
)


@dataclass(frozen=True)
class RoutingDecision:
    mode: str
    query_classification: str
    confidence: float
    forced_hybrid: bool
    escalation_reason: str | None
    recommended_next_action: str


class RetrievalRouter:
    def __init__(self, classifier: RetrievalQueryClassifier | None = None) -> None:
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


# --- Step 104: Source Register retrieval modes ---

def classify_source_query(query_text: str) -> str:
    q = query_text.lower()
    # Lifecycle keywords take precedence (e.g. "retract source" -> lifecycle)
    if any(w in q for w in ["retract", "invalidate", "status", "lifecycle", "archive"]):
        return "source_lifecycle"
    if any(w in q for w in ["source", "find", "discover", "register", "lookup"]):
        return "source_discovery"
    return "general"
def route_to_source_register(query_text: str, payload: dict) -> dict:
    """Route source-oriented queries to structured retriever over source_register."""
    from retrieval_engine.structured_retriever import search_source_register
    classification = classify_source_query(query_text)
    if classification == "source_discovery":
        return search_source_register(
            project_id=payload.get("project_id"),
            query=payload.get("query"),
            status="active",
        )
    elif classification == "source_lifecycle":
        return search_source_register(
            project_id=payload.get("project_id"),
            query=payload.get("query"),
            status=None,  # all statuses
            include_retracted=True,
        )
    return {"error": "Unroutable source query", "classification": classification}

