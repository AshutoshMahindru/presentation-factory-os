from __future__ import annotations

from deck_builder.export_gate import ExportGate
from deck_builder.narrative_arc_validator import NarrativeArcValidator
from deck_builder.render_python_pptx import build_export_metadata, build_outline_artifact
from deck_builder.slide_schema_validator import SlideSchemaValidator


def thesis_payload() -> dict:
    return {
        "thesis_version_id": "thesis-v2-147",
        "thesis_statement": "Mid-market finance teams will adopt deterministic PFOS outputs.",
        "pillars": [
            {
                "pillar_id": "pillar-growth",
                "statement": "Demand is expanding among teams that need auditable decks.",
                "claim_refs": ["claim-growth"],
            },
            {
                "pillar_id": "pillar-margin",
                "statement": "Workflow automation supports validated contribution margin expansion.",
                "claim_refs": ["claim-margin"],
            },
        ],
    }


def slide_for_thesis_pillar(
    slide_id: str,
    job_type: str,
    headline: str,
    body: str,
    evidence_refs: list[str],
    financial_refs: list[str],
) -> dict:
    return {
        "slide_id": slide_id,
        "job": {
            "type": job_type,
            "required_evidence": evidence_refs,
            "objective": headline,
            "phase": "narrative",
        },
        "content": {
            "headline": headline,
            "body": body,
            "chart_id": None,
            "evidence_refs": evidence_refs,
            "financial_refs": financial_refs,
        },
        "visual_quality": "final_rendered",
        "materiality": "high",
        "narrative_arc": "problem_solution",
    }


def test_thesis_to_export_contract_preserves_evidence_and_financial_lineage() -> None:
    thesis = thesis_payload()
    claim_source_refs = {
        "claim-growth": ["source-market"],
        "claim-margin": ["source-model", "source-market"],
    }
    financial_cells = {
        "FM!ARR_Y3_BASE": {
            "cell_ref": "FM!ARR_Y3_BASE",
            "validation_status": "validated",
            "source_refs": ["source-model"],
            "thesis_pillar_id": "pillar-growth",
        },
        "FM!CM_M18_BASE": {
            "cell_ref": "FM!CM_M18_BASE",
            "validation_status": "validated",
            "source_refs": ["source-model"],
            "thesis_pillar_id": "pillar-margin",
        },
    }
    slides = [
        slide_for_thesis_pillar(
            "slide_growth",
            "establish_market_size",
            "The market supports a scaled PFOS wedge",
            "ARR reaches INR 120 crore by year 3.",
            ["source-market"],
            ["FM!ARR_Y3_BASE"],
        ),
        slide_for_thesis_pillar(
            "slide_margin",
            "request_decision",
            "Approve the operating plan",
            "Contribution margin improves to 38% by month 18.",
            ["source-market", "source-model"],
            ["FM!CM_M18_BASE"],
        ),
    ]

    for slide in slides:
        assert SlideSchemaValidator.from_file().validate(slide).valid is True
        artifact = build_outline_artifact(slide)
        assert artifact.generated is True
        assert artifact.artifact is not None
        assert artifact.artifact["slides"][0]["financial_refs"] == slide["content"]["financial_refs"]

    narrative = NarrativeArcValidator().validate(slides)
    assert narrative.valid is True

    metadata = build_export_metadata(
        slides=slides,
        slide_claim_refs={
            "slide_growth": thesis["pillars"][0]["claim_refs"],
            "slide_margin": thesis["pillars"][1]["claim_refs"],
        },
        claim_source_refs=claim_source_refs,
        financial_cells=financial_cells,
    )

    assert metadata["slide_id_to_claim_refs"] == {
        "slide_growth": ["claim-growth"],
        "slide_margin": ["claim-margin"],
    }
    assert metadata["claim_refs_to_source_refs"] == {
        "claim-growth": ["source-market"],
        "claim-margin": ["source-market", "source-model"],
    }
    assert metadata["financial_refs_to_financial_cells"] == financial_cells

    export_result = ExportGate().evaluate(
        {
            "slides": slides,
            "financial_validation_status": "validated",
            "unsupported_financial_claim_count": 0,
            "financial_cells": financial_cells,
            "sensitive_data_detected": False,
            "pii_exposure_detected": False,
            "artifacts": [],
            "pending_source_retraction_count": 0,
            "unprocessed_outbox_count": 0,
        }
    )

    assert export_result.export_allowed is True
    assert export_result.blocking_reasons == ()


def test_thesis_to_export_blocks_when_downstream_cascade_is_open() -> None:
    slide = slide_for_thesis_pillar(
        "slide_blocked",
        "request_decision",
        "Hold export until the evidence graph settles",
        "Contribution margin improves to 38% by month 18.",
        ["source-withdrawn"],
        ["FM!CM_M18_BASE"],
    )

    result = ExportGate().evaluate(
        {
            "slides": [slide],
            "financial_validation_status": "validated",
            "unsupported_financial_claim_count": 0,
            "financial_cells": {
                "FM!CM_M18_BASE": {
                    "cell_ref": "FM!CM_M18_BASE",
                    "validation_status": "validated",
                }
            },
            "sensitive_data_detected": False,
            "pii_exposure_detected": False,
            "artifacts": [{"id": "FM!CM_M18_BASE", "status": "stale_due_to_retreat"}],
            "pending_source_retraction_count": 1,
            "unprocessed_outbox_count": 1,
        }
    )

    assert result.export_allowed is False
    assert "Pending source retraction cascade must complete before export." in result.blocking_reasons
    assert "Cross-store side effects must be drained before export." in result.blocking_reasons
    assert "FM!CM_M18_BASE: stale_due_to_retreat artifacts cannot be exported." in result.blocking_reasons
