from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable


HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


@dataclass(frozen=True)
class DesignPatternRecord:
    pattern_id: str
    source_id: str
    source_uri: str | None
    title: str
    element_count: int
    layout_density: str
    dominant_columns: int
    color_tokens: tuple[str, ...]
    provenance: dict[str, Any]


class DesignCorpusIngestionError(ValueError):
    pass


class DesignCorpusIngestor:
    """Parse local corpus layout payloads into deterministic pattern records."""

    def ingest(self, corpus_items: Iterable[dict[str, Any]]) -> tuple[DesignPatternRecord, ...]:
        records = [self._ingest_one(item) for item in corpus_items]
        return tuple(sorted(records, key=lambda record: record.pattern_id))

    def _ingest_one(self, item: dict[str, Any]) -> DesignPatternRecord:
        source_id = self._required_string(item, "source_id")
        title = self._required_string(item, "title")
        elements = item.get("elements")
        if not isinstance(elements, list) or not elements:
            raise DesignCorpusIngestionError("elements must be a non-empty list")

        normalized_elements = tuple(self._normalize_element(element) for element in elements)
        canvas = self._normalize_canvas(item.get("canvas", {}))
        coverage = self._coverage(normalized_elements, canvas)
        density = self._density(coverage)
        colors = self._colors(normalized_elements)
        columns = self._dominant_columns(normalized_elements, canvas["width"])
        pattern_id = self._pattern_id(source_id, normalized_elements)

        return DesignPatternRecord(
            pattern_id=pattern_id,
            source_id=source_id,
            source_uri=item.get("source_uri"),
            title=title,
            element_count=len(normalized_elements),
            layout_density=density,
            dominant_columns=columns,
            color_tokens=colors,
            provenance={
                "source_id": source_id,
                "source_uri": item.get("source_uri"),
                "page": item.get("page"),
                "ingestion": "deterministic_local",
            },
        )

    @staticmethod
    def _required_string(item: dict[str, Any], field: str) -> str:
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            raise DesignCorpusIngestionError(f"{field} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _normalize_canvas(canvas: dict[str, Any]) -> dict[str, int]:
        width = canvas.get("width", 1920)
        height = canvas.get("height", 1080)
        if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
            raise DesignCorpusIngestionError("canvas width and height must be numeric")
        if width <= 0 or height <= 0:
            raise DesignCorpusIngestionError("canvas dimensions must be positive")
        return {"width": round(width), "height": round(height)}

    @classmethod
    def _normalize_element(cls, element: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(element, dict):
            raise DesignCorpusIngestionError("each element must be an object")
        element_type = element.get("type", "shape")
        if not isinstance(element_type, str) or not element_type.strip():
            raise DesignCorpusIngestionError("element type must be a non-empty string")
        box = {
            "x": cls._number(element, "x"),
            "y": cls._number(element, "y"),
            "width": cls._positive_number(element, "width"),
            "height": cls._positive_number(element, "height"),
        }
        color = element.get("color")
        normalized_color = cls._normalize_color(color) if color is not None else None
        return {
            "type": element_type.strip(),
            "x": box["x"],
            "y": box["y"],
            "width": box["width"],
            "height": box["height"],
            "color": normalized_color,
        }

    @staticmethod
    def _number(element: dict[str, Any], field: str) -> float:
        value = element.get(field)
        if not isinstance(value, (int, float)):
            raise DesignCorpusIngestionError(f"element {field} must be numeric")
        return round(float(value), 4)

    @classmethod
    def _positive_number(cls, element: dict[str, Any], field: str) -> float:
        value = cls._number(element, field)
        if value <= 0:
            raise DesignCorpusIngestionError(f"element {field} must be positive")
        return value

    @staticmethod
    def _normalize_color(value: Any) -> str:
        if not isinstance(value, str) or not HEX_COLOR_RE.match(value.strip()):
            raise DesignCorpusIngestionError(f"invalid element color: {value}")
        candidate = value.strip()
        if candidate.startswith("#"):
            candidate = candidate[1:]
        if len(candidate) == 3:
            candidate = "".join(char * 2 for char in candidate)
        return f"#{candidate.upper()}"

    @staticmethod
    def _coverage(elements: tuple[dict[str, Any], ...], canvas: dict[str, int]) -> float:
        total_area = sum(element["width"] * element["height"] for element in elements)
        canvas_area = canvas["width"] * canvas["height"]
        return total_area / canvas_area

    @staticmethod
    def _density(coverage: float) -> str:
        if coverage < 0.18:
            return "spacious"
        if coverage > 0.42:
            return "compact"
        return "standard"

    @staticmethod
    def _colors(elements: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
        return tuple(sorted({element["color"] for element in elements if element["color"]}))

    @staticmethod
    def _dominant_columns(elements: tuple[dict[str, Any], ...], canvas_width: int) -> int:
        x_positions = sorted({round(element["x"]) for element in elements})
        if len(x_positions) <= 1:
            return 1
        average_gap = (x_positions[-1] - x_positions[0]) / (len(x_positions) - 1)
        if average_gap <= 0:
            return 1
        inferred = round(canvas_width / average_gap)
        return min(24, max(1, inferred))

    @staticmethod
    def _pattern_id(source_id: str, elements: tuple[dict[str, Any], ...]) -> str:
        signatures = [
            f"{element['type']}:{element['x']}:{element['y']}:{element['width']}:{element['height']}:{element['color']}"
            for element in elements
        ]
        digest = hashlib.sha256(f"{source_id}|{'|'.join(sorted(signatures))}".encode("utf-8")).hexdigest()
        return f"pattern_{digest[:16]}"
