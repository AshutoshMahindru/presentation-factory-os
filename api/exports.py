from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from deck_builder.render_pdf import render_pdf_manifest
from deck_builder.render_speaker_notes import render_speaker_notes
from deck_builder.render_web_deck import render_web_deck


SUPPORTED_FORMATS = ("pptx", "pdf", "web", "speaker_notes")


@dataclass(frozen=True)
class ExportArtifact:
    format: str
    mime_type: str
    content_hash: str
    metadata: dict[str, Any]


def export_deck(deck: dict[str, Any], formats: tuple[str, ...] | list[str] | None = None) -> dict[str, Any]:
    requested = tuple(formats or SUPPORTED_FORMATS)
    unknown = sorted(set(requested) - set(SUPPORTED_FORMATS))
    if unknown:
        raise ValueError(f"unsupported export formats: {', '.join(unknown)}")

    artifacts: list[ExportArtifact] = []
    for fmt in requested:
        if fmt == "web":
            rendered = render_web_deck(deck)
            artifacts.append(
                ExportArtifact(
                    format="web",
                    mime_type="text/html",
                    content_hash=rendered.content_hash,
                    metadata={"slide_count": rendered.slide_count, "warnings": list(rendered.warnings)},
                )
            )
        elif fmt == "pdf":
            manifest = render_pdf_manifest(deck)
            artifacts.append(
                ExportArtifact(
                    format="pdf",
                    mime_type=manifest["mime_type"],
                    content_hash=manifest["content_hash"],
                    metadata=manifest,
                )
            )
        elif fmt == "speaker_notes":
            notes = render_speaker_notes(deck)
            artifacts.append(
                ExportArtifact(
                    format="speaker_notes",
                    mime_type=notes["mime_type"],
                    content_hash=notes["content_hash"],
                    metadata={"text": notes["text"]},
                )
            )
        elif fmt == "pptx":
            slide_ids = [str(slide.get("slide_id") or index) for index, slide in enumerate(deck.get("slides", []) or [], start=1)]
            digest = sha256(("pptx\n" + "\n".join(slide_ids)).encode("utf-8")).hexdigest()
            artifacts.append(
                ExportArtifact(
                    format="pptx",
                    mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    content_hash=digest,
                    metadata={"slide_count": len(slide_ids), "slide_ids": slide_ids},
                )
            )

    return {
        "metadata_type": "multi_format_export",
        "formats": [artifact.format for artifact in artifacts],
        "artifacts": [artifact.__dict__ for artifact in artifacts],
    }
