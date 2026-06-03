from __future__ import annotations

from hashlib import sha256
from typing import Any


def render_pdf_manifest(deck: dict[str, Any]) -> dict[str, Any]:
    slides = deck.get("slides", []) or []
    slide_ids = [str(slide.get("slide_id") or f"slide_{index:03d}") for index, slide in enumerate(slides, start=1)]
    joined = "\n".join(slide_ids)
    return {
        "format": "pdf",
        "mime_type": "application/pdf",
        "slide_count": len(slide_ids),
        "slide_ids": slide_ids,
        "content_hash": sha256(joined.encode("utf-8")).hexdigest(),
    }
