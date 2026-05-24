from deck_builder.render_python_pptx import build_outline_artifact


def valid_slide_payload():
    return {
        "slide_id": "slide_001",
        "job": {
            "type": "establish_market_size",
            "required_evidence": ["source_001"],
            "objective": "Show the size of the market opportunity",
            "phase": "narrative",
        },
        "content": {
            "headline": "The market is large enough to support venture-scale growth",
            "body": "The addressable market is attractive and evidence-backed.",
            "chart_id": None,
            "evidence_refs": ["source_001"],
            "financial_refs": [],
        },
        "visual_quality": "code_generated",
        "materiality": "high",
        "narrative_arc": "problem_solution",
    }


def test_valid_slide_job_generates_deterministic_outline_artifact():
    first = build_outline_artifact(valid_slide_payload())
    second = build_outline_artifact(valid_slide_payload())

    assert first.generated is True
    assert first.blocking_reasons == ()
    assert first.artifact == second.artifact
    assert first.artifact["artifact_type"] == "deck_outline"
    assert first.artifact["slides"][0]["slide_id"] == "slide_001"
    assert len(first.artifact["input_hash"]) == 64


def test_invalid_slide_job_returns_blocked_reason():
    payload = valid_slide_payload()
    payload["visual_quality"] = "hand_drawn"

    result = build_outline_artifact(payload)

    assert result.generated is False
    assert result.artifact is None
    assert any("visual_quality" in reason for reason in result.blocking_reasons)
