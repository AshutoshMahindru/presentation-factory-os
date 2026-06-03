from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from deck_builder.visual_regression import reference_hash


def generate_reference_set(decks: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {name: reference_hash(deck) for name, deck in sorted(decks.items())}


def write_reference_set(path: str | Path, decks: dict[str, dict[str, Any]]) -> dict[str, str]:
    references = generate_reference_set(decks)
    output_path = Path(path)
    output_path.write_text(json.dumps(references, indent=2, sort_keys=True) + "\n")
    return references
