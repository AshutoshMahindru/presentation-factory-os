from dataclasses import dataclass

from retrieval_engine.classifiers import QueryClassification, QueryClassifier
from retrieval_engine.router import RetrievalRouter
from retrieval_engine.standard_payload import StandardContextPayloadValidator


def test_financial_query_routes_structured_without_exact_keyword_counting():
    decision = RetrievalRouter().route(
        "How sensitive is runway if enterprise bookings slip?"
    )

    assert decision.query_classification == "financial"
    assert decision.mode == "structured"
    assert decision.confidence > 0.5


def test_strategic_query_routes_hybrid_from_profile_similarity():
    decision = RetrievalRouter().route("What is our moat against incumbent retaliation?")

    assert decision.query_classification == "strategic"
    assert decision.mode == "hybrid"
    assert decision.forced_hybrid is True


def test_narrative_query_routes_semantic_from_story_structure():
    decision = RetrievalRouter().route("Move the opening hook before the proof points.")

    assert decision.query_classification == "narrative"
    assert decision.mode == "semantic"


def test_visual_query_routes_semantic_from_layout_language():
    decision = RetrievalRouter().route(
        "Make the comparison page less cluttered and easier to scan."
    )

    assert decision.query_classification == "visual"
    assert decision.mode == "semantic"


def test_unknown_low_confidence_query_routes_hybrid_with_gap_payload():
    payload = RetrievalRouter().build_empty_payload("banana umbrella syntax")

    assert payload["routing_decision"]["mode"] == "hybrid"
    assert payload["routing_decision"]["validation_metadata"][
        "query_classification"
    ] == "unknown"
    assert payload["routing_decision"]["validation_metadata"]["forced_hybrid"] is True
    assert payload["gaps"] == [
        {
            "gap_type": "scope_mismatch",
            "description": "Query could not be confidently classified.",
            "severity": "warning",
        }
    ]
    assert "specific query" in payload["recommended_next_action"]
    assert StandardContextPayloadValidator.from_file().validate(payload).valid is True


def test_mode_hint_preserves_graph_route_mode():
    decision = RetrievalRouter().route("trace the evidence graph", mode_hint="graph")

    assert decision.mode == "graph"
    assert decision.forced_hybrid is False
    assert decision.recommended_next_action == "Use caller-specified retrieval mode."


def test_router_accepts_pluggable_classifier():
    @dataclass(frozen=True)
    class StubClassifier:
        def classify(self, query: str) -> QueryClassification:
            return QueryClassification(
                query_classification="visual",
                confidence=0.87,
                reason=f"stubbed for {query}",
            )

    decision = RetrievalRouter(classifier=StubClassifier()).route("anything")

    assert decision.query_classification == "visual"
    assert decision.mode == "semantic"
    assert decision.confidence == 0.87


def test_default_classifier_is_local_deterministic_fallback():
    classifier = QueryClassifier()

    first = classifier.classify("How sensitive is runway if enterprise bookings slip?")
    second = classifier.classify("How sensitive is runway if enterprise bookings slip?")

    assert first == second
    assert first.query_classification == "financial"
