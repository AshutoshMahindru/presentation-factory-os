from retrieval_engine.router import RetrievalRouter
from retrieval_engine.standard_payload import StandardContextPayloadValidator


def test_financial_query_routes_structured():
    decision = RetrievalRouter().route("Show revenue margin and IRR from the model")
    assert decision.query_classification == "financial"
    assert decision.mode == "structured"


def test_strategic_claim_query_routes_hybrid():
    decision = RetrievalRouter().route("Find contradiction in market size evidence claim")
    assert decision.query_classification == "strategic"
    assert decision.mode == "hybrid"
    assert decision.forced_hybrid is True


def test_narrative_query_routes_semantic():
    decision = RetrievalRouter().route("Improve the story flow and objection preemption")
    assert decision.query_classification == "narrative"
    assert decision.mode == "semantic"


def test_visual_query_routes_semantic():
    decision = RetrievalRouter().route("Check chart legibility and slide layout density")
    assert decision.query_classification == "visual"
    assert decision.mode == "semantic"


def test_unknown_query_routes_hybrid_with_gap_payload():
    payload = RetrievalRouter().build_empty_payload("banana umbrella syntax")

    assert payload["routing_decision"]["mode"] == "hybrid"
    assert payload["routing_decision"]["validation_metadata"]["query_classification"] == "unknown"
    assert payload["gaps"][0]["gap_type"] == "scope_mismatch"

    result = StandardContextPayloadValidator.from_file().validate(payload)
    assert result.valid is True
