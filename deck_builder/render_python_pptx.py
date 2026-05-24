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
    claim_refs_to_source_refs: dict[str, list[str]] = {}
    financial_refs_to_cells: dict[str, dict[str, Any] | None] = {}

    for slide in slides:
        slide_id = str(slide["slide_id"])
        claim_refs = sorted(slide_claim_refs.get(slide_id, []))
        slide_to_claim_refs[slide_id] = claim_refs

        for claim_ref in claim_refs:
            claim_refs_to_source_refs[claim_ref] = sorted(claim_source_refs.get(claim_ref, []))

        for financial_ref in sorted(slide.get("content", {}).get("financial_refs", []) or []):
            financial_refs_to_cells[financial_ref] = financial_cells.get(financial_ref)

    return {
        "metadata_type": "deck_export_metadata",
        "schema_version": "1.0",
        "slide_id_to_claim_refs": slide_to_claim_refs,
        "claim_refs_to_source_refs": dict(sorted(claim_refs_to_source_refs.items())),
        "financial_refs_to_financial_cells": dict(sorted(financial_refs_to_cells.items())),
    }


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
