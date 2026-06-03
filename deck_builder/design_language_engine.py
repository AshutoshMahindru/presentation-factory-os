from __future__ import annotations

from dataclasses import dataclass
from typing import Any


Density = str


@dataclass(frozen=True)
class DesignLanguageInput:
    base_color: str = "#1F4E79"
    accent_color: str | None = None
    density: Density = "standard"
    canvas_width: int = 1920
    canvas_height: int = 1080
    grid_columns: int = 12
    base_font_size: int = 16
    type_scale: float = 1.25
    font_family: str = "Inter"


@dataclass(frozen=True)
class DesignLanguageSystem:
    tokens: tuple[dict[str, Any], ...]
    grid: dict[str, Any]
    type_scale: dict[str, int]
    color_harmony: dict[str, str]

    def token_map(self) -> dict[str, Any]:
        return {token["name"]: token["value"] for token in self.tokens}


class DesignLanguageEngine:
    """Deterministic mathematical design language generator."""

    _DENSITY_BASE_SPACING = {
        "compact": 6,
        "standard": 8,
        "spacious": 10,
    }

    def generate(self, intent: DesignLanguageInput | dict[str, Any] | None = None) -> DesignLanguageSystem:
        design_input = self._coerce_input(intent)
        self._validate_input(design_input)

        spacing_base = self._DENSITY_BASE_SPACING[design_input.density]
        grid = self._grid(design_input, spacing_base)
        type_scale = self._type_scale(design_input)
        colors = self._color_harmony(design_input)

        tokens = (
            self._token("layout", "layout.canvas.width", "dimension", design_input.canvas_width, "px"),
            self._token("layout", "layout.canvas.height", "dimension", design_input.canvas_height, "px"),
            self._token("layout", "layout.grid.columns", "number", design_input.grid_columns, None),
            self._token("layout", "layout.grid.margin", "spacing", grid["margin"], "px"),
            self._token("layout", "layout.grid.gutter", "spacing", grid["gutter"], "px"),
            self._token("spacing", "spacing.xs", "spacing", spacing_base, "px"),
            self._token("spacing", "spacing.sm", "spacing", spacing_base * 2, "px"),
            self._token("spacing", "spacing.md", "spacing", spacing_base * 3, "px"),
            self._token("spacing", "spacing.lg", "spacing", spacing_base * 5, "px"),
            self._token("spacing", "spacing.xl", "spacing", spacing_base * 8, "px"),
            self._token("typography", "typography.font.family.body", "font_family", design_input.font_family, None),
            self._token("typography", "typography.font.size.body", "font_size", type_scale["body"], "pt"),
            self._token("typography", "typography.font.size.caption", "font_size", type_scale["caption"], "pt"),
            self._token("typography", "typography.font.size.h3", "font_size", type_scale["h3"], "pt"),
            self._token("typography", "typography.font.size.h2", "font_size", type_scale["h2"], "pt"),
            self._token("typography", "typography.font.size.h1", "font_size", type_scale["h1"], "pt"),
            self._token("color", "color.brand.primary", "color", colors["primary"], "hex"),
            self._token("color", "color.brand.secondary", "color", colors["secondary"], "hex"),
            self._token("color", "color.brand.accent", "color", colors["accent"], "hex"),
            self._token("color", "color.neutral.ink", "color", colors["ink"], "hex"),
            self._token("color", "color.neutral.canvas", "color", colors["canvas"], "hex"),
            self._token("component", "component.card.radius", "radius", 8, "px"),
            self._token("chart", "chart.series.count", "number", 6, None),
        )
        return DesignLanguageSystem(tokens=tokens, grid=grid, type_scale=type_scale, color_harmony=colors)

    @classmethod
    def _coerce_input(cls, intent: DesignLanguageInput | dict[str, Any] | None) -> DesignLanguageInput:
        if intent is None:
            return DesignLanguageInput()
        if isinstance(intent, DesignLanguageInput):
            return intent
        return DesignLanguageInput(**intent)

    @classmethod
    def _validate_input(cls, intent: DesignLanguageInput) -> None:
        if intent.density not in cls._DENSITY_BASE_SPACING:
            raise ValueError(f"Unsupported density: {intent.density}")
        if intent.grid_columns < 4 or intent.grid_columns > 24:
            raise ValueError("grid_columns must be between 4 and 24")
        if intent.canvas_width <= 0 or intent.canvas_height <= 0:
            raise ValueError("canvas dimensions must be positive")
        if intent.base_font_size < 8 or intent.base_font_size > 32:
            raise ValueError("base_font_size must be between 8 and 32")
        if intent.type_scale < 1.05 or intent.type_scale > 1.6:
            raise ValueError("type_scale must be between 1.05 and 1.6")
        cls._parse_hex(intent.base_color)
        if intent.accent_color:
            cls._parse_hex(intent.accent_color)

    @staticmethod
    def _grid(intent: DesignLanguageInput, spacing_base: int) -> dict[str, Any]:
        margin = spacing_base * 8
        gutter = spacing_base * 3
        available_width = intent.canvas_width - (margin * 2) - (gutter * (intent.grid_columns - 1))
        column_width = round(available_width / intent.grid_columns, 2)
        baseline = spacing_base
        return {
            "columns": intent.grid_columns,
            "margin": margin,
            "gutter": gutter,
            "column_width": column_width,
            "baseline": baseline,
        }

    @staticmethod
    def _type_scale(intent: DesignLanguageInput) -> dict[str, int]:
        body = intent.base_font_size
        return {
            "caption": round(body / intent.type_scale),
            "body": body,
            "h3": round(body * intent.type_scale),
            "h2": round(body * intent.type_scale**2),
            "h1": round(body * intent.type_scale**3),
        }

    @classmethod
    def _color_harmony(cls, intent: DesignLanguageInput) -> dict[str, str]:
        primary = cls._normalize_hex(intent.base_color)
        secondary = cls._rotate_hue(primary, 30)
        accent = cls._normalize_hex(intent.accent_color) if intent.accent_color else cls._rotate_hue(primary, 180)
        return {
            "primary": primary,
            "secondary": secondary,
            "accent": accent,
            "ink": "#1B1F24",
            "canvas": "#FFFFFF",
        }

    @staticmethod
    def _token(
        namespace: str,
        name: str,
        token_type: str,
        value: str | int | float | bool | dict[str, Any] | list[Any],
        unit: str | None,
    ) -> dict[str, Any]:
        return {
            "namespace": namespace,
            "name": name,
            "type": token_type,
            "value": value,
            "unit": unit,
            "source": "generated",
            "description": f"Generated deterministic {name} token.",
        }

    @classmethod
    def _normalize_hex(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("color value is required")
        red, green, blue = cls._parse_hex(value)
        return f"#{red:02X}{green:02X}{blue:02X}"

    @staticmethod
    def _parse_hex(value: str) -> tuple[int, int, int]:
        candidate = value.strip()
        if candidate.startswith("#"):
            candidate = candidate[1:]
        if len(candidate) == 3:
            candidate = "".join(char * 2 for char in candidate)
        if len(candidate) != 6:
            raise ValueError(f"Invalid hex color: {value}")
        try:
            red = int(candidate[0:2], 16)
            green = int(candidate[2:4], 16)
            blue = int(candidate[4:6], 16)
        except ValueError as exc:
            raise ValueError(f"Invalid hex color: {value}") from exc
        return red, green, blue

    @classmethod
    def _rotate_hue(cls, value: str, degrees: int) -> str:
        red, green, blue = cls._parse_hex(value)
        channels = [red, green, blue]
        rotations = (degrees // 120) % 3
        for _ in range(rotations):
            channels = [channels[2], channels[0], channels[1]]
        if degrees % 120:
            shift = degrees % 120
            channels = [(channel + shift) % 256 for channel in channels]
        return f"#{channels[0]:02X}{channels[1]:02X}{channels[2]:02X}"
