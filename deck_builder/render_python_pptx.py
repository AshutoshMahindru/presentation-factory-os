from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from deck_builder.slide_schema_validator import SlideSchemaValidator


@dataclass(frozen=True)
class DeckArtifactResult:
    generated: bool
    artifact: dict[str, Any] | None
    blocking_reasons: tuple[str, ...]


def build_outline_artifact(slide_job: dict[str, Any]) -> DeckArtifactResult:
    """
    Build the minimal deterministic deck artifact used before PPTX rendering exists.

    This intentionally returns an outline payload, not a binary PPTX. Invalid slide
    jobs are blocked with schema validation reasons so callers can fail closed.
    """

    validation = SlideSchemaValidator.from_file().validate(slide_job)
    if not validation.valid:
        return DeckArtifactResult(
            generated=False,
            artifact=None,
            blocking_reasons=validation.errors,
        )

    content = slide_job["content"]
    artifact = {
        "artifact_type": "deck_outline",
        "schema_version": "1.0",
        "input_hash": _canonical_hash(slide_job),
        "slides": [
            {
                "slide_id": slide_job["slide_id"],
                "job_type": slide_job["job"]["type"],
                "headline": content["headline"],
                "body": content["body"],
                "chart_id": content.get("chart_id"),
                "evidence_refs": list(content.get("evidence_refs", [])),
                "financial_refs": list(content.get("financial_refs", [])),
                "visual_quality": slide_job["visual_quality"],
                "materiality": slide_job["materiality"],
            }
        ],
    }

    return DeckArtifactResult(
        generated=True,
        artifact=artifact,
        blocking_reasons=(),
    )


def build_export_metadata(
    slides: list[dict[str, Any]],
    slide_claim_refs: dict[str, list[str]],
    claim_source_refs: dict[str, list[str]],
    financial_cells: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Build deterministic export metadata used by appendices and evidence maps.

    The function is intentionally side-effect free. It does not validate whether
    references are complete; later gates decide whether missing refs block export.
    """

    slide_to_claim_refs: dict[str, list[str]] = {}
    slide_to_evidence_refs: dict[str, list[str]] = {}
    slide_to_financial_refs: dict[str, list[str]] = {}
    slide_to_materiality: dict[str, str] = {}
    claim_refs_to_source_refs: dict[str, list[str]] = {}
    financial_refs_to_cells: dict[str, dict[str, Any] | None] = {}
    source_refs_to_claim_refs: dict[str, set[str]] = {}
    source_refs_to_slide_ids: dict[str, set[str]] = {}

    for slide in slides:
        slide_id = str(slide["slide_id"])
        claim_refs = sorted(slide_claim_refs.get(slide_id, []))
        slide_to_claim_refs[slide_id] = claim_refs
        slide_to_materiality[slide_id] = str(slide.get("materiality", ""))

        content = slide.get("content", {})
        evidence_refs = sorted(str(ref) for ref in content.get("evidence_refs", []) or [])
        financial_refs = sorted(str(ref) for ref in content.get("financial_refs", []) or [])
        slide_to_evidence_refs[slide_id] = evidence_refs
        slide_to_financial_refs[slide_id] = financial_refs

        for claim_ref in claim_refs:
            source_refs = sorted(claim_source_refs.get(claim_ref, []))
            claim_refs_to_source_refs[claim_ref] = source_refs
            for source_ref in source_refs:
                source_refs_to_claim_refs.setdefault(source_ref, set()).add(claim_ref)
                source_refs_to_slide_ids.setdefault(source_ref, set()).add(slide_id)

        for evidence_ref in evidence_refs:
            source_refs_to_slide_ids.setdefault(evidence_ref, set()).add(slide_id)

        for financial_ref in financial_refs:
            financial_refs_to_cells[financial_ref] = financial_cells.get(financial_ref)

    source_appendix = {
        source_ref: {
            "claim_refs": sorted(source_refs_to_claim_refs.get(source_ref, set())),
            "slide_ids": sorted(source_refs_to_slide_ids.get(source_ref, set())),
        }
        for source_ref in sorted(source_refs_to_slide_ids)
    }

    return {
        "metadata_type": "deck_export_metadata",
        "schema_version": "1.0",
        "slide_id_to_claim_refs": slide_to_claim_refs,
        "slide_id_to_evidence_refs": slide_to_evidence_refs,
        "slide_id_to_financial_refs": slide_to_financial_refs,
        "slide_id_to_materiality": slide_to_materiality,
        "claim_refs_to_source_refs": dict(sorted(claim_refs_to_source_refs.items())),
        "source_refs_to_claim_refs": {
            source_ref: sorted(claim_refs)
            for source_ref, claim_refs in sorted(source_refs_to_claim_refs.items())
        },
        "source_appendix": source_appendix,
        "financial_refs_to_financial_cells": dict(sorted(financial_refs_to_cells.items())),
    }


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
