from datetime import UTC, datetime
from uuid import uuid4

import pytest

from retrieval_engine.standard_payload import (
    RetrievalPayloadValidationError,
    StandardContextPayloadValidator,
)


def valid_payload():
    return {
        "request_id": str(uuid4()),
        "query": "Find sourced claims about market size.",
        "routing_decision": {
            "mode": "hybrid",
            "validation_metadata": {
                "query_classification": "strategic",
                "forced_hybrid": True,
                "escalation_reason": "Strategic query requires both semantic and graph validation.",
            },
        },
        "items": [
            {
                "id": "claim_001",
                "type": "claim",
                "content": "The addressable market is large enough to support venture-scale growth.",
                "source_ref": "source_001",
                "confidence": 0.91,
                "metadata": {"materiality": "high"},
            }
        ],
        "provenance": {
            "retrieved_at": datetime.now(UTC).isoformat(),
            "retrieval_engine_version": "3.2.4",
            "stores_queried": ["postgres", "neo4j", "qdrant"],
            "trace_id": str(uuid4()),
        },
        "confidence": 0.88,
        "gaps": [],
        "recommended_next_action": "Proceed with graph-backed narrative synthesis.",
    }


def test_valid_standard_context_payload_passes():
    validator = StandardContextPayloadValidator.from_file()
    result = validator.validate(valid_payload())
    assert result.valid is True
    assert result.errors == ()


def test_missing_request_id_fails():
    validator = StandardContextPayloadValidator.from_file()
    payload = valid_payload()
    payload.pop("request_id")

    result = validator.validate(payload)

    assert result.valid is False
    assert any("request_id" in error for error in result.errors)


def test_invalid_routing_mode_fails():
    validator = StandardContextPayloadValidator.from_file()
    payload = valid_payload()
    payload["routing_decision"]["mode"] = "random"

    with pytest.raises(RetrievalPayloadValidationError):
        validator.assert_valid(payload)


def test_invalid_query_classification_fails():
    validator = StandardContextPayloadValidator.from_file()
    payload = valid_payload()
    payload["routing_decision"]["validation_metadata"]["query_classification"] = "legal"

    result = validator.validate(payload)

    assert result.valid is False
    assert any("query_classification" in error for error in result.errors)


def test_item_confidence_must_be_between_zero_and_one():
    validator = StandardContextPayloadValidator.from_file()
    payload = valid_payload()
    payload["items"][0]["confidence"] = 1.5

    result = validator.validate(payload)

    assert result.valid is False
    assert any("confidence" in error for error in result.errors)


def test_gap_type_enum_is_enforced():
    validator = StandardContextPayloadValidator.from_file()
    payload = valid_payload()
    payload["gaps"] = [
        {
            "gap_type": "not_a_real_gap",
            "description": "Invalid gap type should fail.",
            "severity": "warning",
        }
    ]

    result = validator.validate(payload)

    assert result.valid is False
    assert any("gap_type" in error for error in result.errors)
