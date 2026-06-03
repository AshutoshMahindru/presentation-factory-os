from deck_builder.render_python_pptx import build_export_metadata, build_outline_artifact


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


def test_build_export_metadata_maps_slides_claims_sources_and_financial_cells():
    slide = valid_slide_payload()
    slide["content"]["financial_refs"] = ["FM!CM_M18_BASE"]
    slide["content"]["evidence_refs"] = ["source_001"]

    metadata = build_export_metadata(
        slides=[slide],
        slide_claim_refs={"slide_001": ["claim_002", "claim_001"]},
        claim_source_refs={
            "claim_001": ["source_002", "source_001"],
            "claim_002": ["source_003"],
        },
        financial_cells={
            "FM!CM_M18_BASE": {
                "cell_ref": "FM!CM_M18_BASE",
                "validation_status": "validated",
            }
        },
    )

    assert metadata == {
        "metadata_type": "deck_export_metadata",
        "schema_version": "1.0",
        "slide_id_to_claim_refs": {"slide_001": ["claim_001", "claim_002"]},
        "slide_id_to_evidence_refs": {"slide_001": ["source_001"]},
        "slide_id_to_financial_refs": {"slide_001": ["FM!CM_M18_BASE"]},
        "slide_id_to_materiality": {"slide_001": "high"},
        "claim_refs_to_source_refs": {
            "claim_001": ["source_001", "source_002"],
            "claim_002": ["source_003"],
        },
        "source_refs_to_claim_refs": {
            "source_001": ["claim_001"],
            "source_002": ["claim_001"],
            "source_003": ["claim_002"],
        },
        "source_appendix": {
            "source_001": {
                "claim_refs": ["claim_001"],
                "slide_ids": ["slide_001"],
            },
            "source_002": {
                "claim_refs": ["claim_001"],
                "slide_ids": ["slide_001"],
            },
            "source_003": {
                "claim_refs": ["claim_002"],
                "slide_ids": ["slide_001"],
            },
        },
        "financial_refs_to_financial_cells": {
            "FM!CM_M18_BASE": {
                "cell_ref": "FM!CM_M18_BASE",
                "validation_status": "validated",
            }
        },
    }


def test_build_export_metadata_includes_direct_evidence_without_claim_mapping():
    slide = valid_slide_payload()
    slide["content"]["evidence_refs"] = ["source_direct"]

    metadata = build_export_metadata(
        slides=[slide],
        slide_claim_refs={},
        claim_source_refs={},
        financial_cells={},
    )

    assert metadata["source_appendix"] == {
        "source_direct": {
            "claim_refs": [],
            "slide_ids": ["slide_001"],
        }
    }
