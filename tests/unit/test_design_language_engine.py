import pytest

from deck_builder.design_language_engine import DesignLanguageEngine, DesignLanguageInput
from deck_builder.design_token_validator import DesignTokenValidator


def test_design_language_generation_is_deterministic_and_schema_valid():
    engine = DesignLanguageEngine()
    intent = DesignLanguageInput(
        base_color="#336699",
        density="standard",
        canvas_width=1600,
        canvas_height=900,
        grid_columns=10,
        base_font_size=18,
        type_scale=1.2,
    )

    first = engine.generate(intent)
    second = engine.generate(intent)

    assert first == second
    assert first.grid == {
        "columns": 10,
        "margin": 64,
        "gutter": 24,
        "column_width": 125.6,
        "baseline": 8,
    }
    assert first.type_scale == {
        "caption": 15,
        "body": 18,
        "h3": 22,
        "h2": 26,
        "h1": 31,
    }
    assert first.color_harmony["primary"] == "#336699"

    validation = DesignTokenValidator.from_file().validate_many(first.tokens)
    assert validation.valid is True


def test_design_language_density_controls_spacing_tokens():
    compact = DesignLanguageEngine().generate({"density": "compact"}).token_map()
    spacious = DesignLanguageEngine().generate({"density": "spacious"}).token_map()

    assert compact["spacing.md"] == 18
    assert spacious["spacing.md"] == 30
    assert compact["layout.grid.gutter"] < spacious["layout.grid.gutter"]


def test_design_language_rejects_invalid_constraints():
    with pytest.raises(ValueError, match="grid_columns"):
        DesignLanguageEngine().generate({"grid_columns": 2})

    with pytest.raises(ValueError, match="Invalid hex color"):
        DesignLanguageEngine().generate({"base_color": "not-a-color"})
