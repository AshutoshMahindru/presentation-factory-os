from __future__ import annotations

from typing import Any

from api.exports import export_deck


def build_export_response(deck: dict[str, Any], formats: list[str] | None = None) -> dict[str, Any]:
    return export_deck(deck, formats=formats)
