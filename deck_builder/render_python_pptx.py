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


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
