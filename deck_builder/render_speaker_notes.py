from __future__ import annotations

from hashlib import sha256
from typing import Any


def render_speaker_notes(deck: dict[str, Any]) -> dict[str, Any]:
    lines: list[str] = []
    for index, slide in enumerate(deck.get("slides", []) or [], start=1):
        slide_id = str(slide.get("slide_id") or f"slide_{index:03d}")
        notes = str(slide.get("speaker_notes") or slide.get("notes") or "")
        lines.append(f"{slide_id}: {notes}".rstrip())
    text = "\n".join(lines)
    return {
        "format": "speaker_notes",
        "mime_type": "text/plain",
        "text": text,
        "content_hash": sha256(text.encode("utf-8")).hexdigest(),
    }
