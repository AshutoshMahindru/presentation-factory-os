from deck_builder.export_gate import ExportGate
from deck_builder.narrative_arc_validator import NarrativeArcValidator
from deck_builder.render_python_pptx import build_export_metadata, build_outline_artifact
from deck_builder.slide_schema_validator import SlideSchemaValidator


def test_golden_path_brief_to_export():
    project = {
        "project_id": "project_001",
        "brief": "Show market size and contribution margin readiness.",
        "phase": "created",
    }

    source = {
        "source_id": "source_001",
        "status": "active",
        "title": "Market evidence packet",
    }
    claim = {
        "claim_ref": "claim_001",
        "status": "supported",
        "source_refs": [source["source_id"]],
    }

    financial_cell = {
        "cell_ref": "FM!CM_M18_BASE",
        "validation_status": "validated",
        "formula": "=Revenue-Cost",
    }

    slide_job = {
        "slide_id": "slide_001",
        "job": {
            "type": "establish_market_size",
            "required_evidence": [source["source_id"]],
            "objective": "Show evidence-backed readiness",
            "phase": "narrative",
        },
        "content": {
            "headline": "The market supports a financially credible launch",
            "body": "Contribution margin improves to 38% by month 18.",
            "chart_id": None,
            "evidence_refs": [source["source_id"]],
            "financial_refs": [financial_cell["cell_ref"]],
        },
        "visual_quality": "final_rendered",
        "materiality": "high",
        "narrative_arc": "problem_solution",
    }

    project["phase"] = "research"
    assert source["status"] == "active"
    assert claim["status"] == "supported"

    project["phase"] = "financial_model"
    assert financial_cell["validation_status"] == "validated"

    project["phase"] = "narrative"
    slide_validation = SlideSchemaValidator.from_file().validate(slide_job)
    assert slide_validation.valid is True

    narrative_validation = NarrativeArcValidator().validate([slide_job])
    assert narrative_validation.valid is True

    project["phase"] = "visual_design"
    visual_qa = {"status": "passed", "score": 5}
    assert visual_qa["status"] == "passed"

    project["phase"] = "approved"
    approval = {"status": "approved", "approver_role": "operator"}
    assert approval["status"] == "approved"

    deck = {
        "slides": [slide_job],
        "financial_validation_status": "validated",
        "unsupported_financial_claim_count": 0,
        "financial_cells": {
            financial_cell["cell_ref"]: financial_cell,
        },
        "sensitive_data_detected": False,
        "pii_exposure_detected": False,
        "artifacts": [],
        "pending_source_retraction_count": 0,
        "unprocessed_outbox_count": 0,
    }
    export_result = ExportGate().evaluate(deck)
    assert export_result.export_allowed is True

    artifact_result = build_outline_artifact(slide_job)
    assert artifact_result.generated is True

    metadata = build_export_metadata(
        slides=[slide_job],
        slide_claim_refs={slide_job["slide_id"]: [claim["claim_ref"]]},
        claim_source_refs={claim["claim_ref"]: claim["source_refs"]},
        financial_cells={financial_cell["cell_ref"]: financial_cell},
    )
    assert metadata["slide_id_to_claim_refs"] == {"slide_001": ["claim_001"]}
    assert metadata["claim_refs_to_source_refs"] == {"claim_001": ["source_001"]}
    assert metadata["financial_refs_to_financial_cells"] == {
        "FM!CM_M18_BASE": financial_cell
    }

    project["phase"] = "exported"
    assert project["phase"] == "exported"
