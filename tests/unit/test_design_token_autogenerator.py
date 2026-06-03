from deck_builder.design_language_engine import DesignLanguageEngine
from deck_builder.design_token_autogenerator import (
    DesignTokenAutogenerator,
    TokenAutogenerationRules,
)
from deck_builder.design_token_validator import DesignTokenValidator


def _seed_tokens():
    system = DesignLanguageEngine().generate({"base_color": "#336699", "density": "standard"})
    return system.tokens


def test_autogenerator_creates_bounded_schema_valid_variants():
    result = DesignTokenAutogenerator().generate(_seed_tokens())

    assert result.rejected == ()
    assert len(result.tokens) > 0
    assert all(token["source"] == "generated" for token in result.tokens)
    assert all(token["name"].count(".") >= 2 for token in result.tokens)
    assert DesignTokenValidator.from_file().validate_many(result.tokens).valid is True

    names = {token["name"] for token in result.tokens}
    assert "color.brand.primary.tint" in names
    assert "color.brand.primary.shade" in names
    assert "spacing.md.compact" in names
    assert "spacing.md.spacious" in names


def test_autogenerator_respects_max_variants_per_seed():
    seed = [
        {
            "namespace": "spacing",
            "name": "spacing.md",
            "type": "spacing",
            "value": 24,
            "unit": "px",
            "source": "generated",
            "description": "seed",
        }
    ]
    result = DesignTokenAutogenerator(
        rules=TokenAutogenerationRules(max_variants_per_token=1)
    ).generate(seed)

    assert [token["name"] for token in result.tokens] == ["spacing.md.compact"]


def test_autogenerator_rejects_invalid_seed_without_remote_dependency():
    invalid_schema_token = {
        "namespace": "vibes",
        "name": "bad",
        "type": "spacing",
        "value": 8,
    }
    invalid_color_token = {
        "namespace": "color",
        "name": "color.brand.bad",
        "type": "color",
        "value": "blue",
        "unit": "hex",
        "source": "generated",
        "description": "seed",
    }

    result = DesignTokenAutogenerator().generate([invalid_schema_token, invalid_color_token])

    assert result.tokens == ()
    assert len(result.rejected) == 2
    assert "bad" in result.rejected[0]
    assert "Invalid hex color" in result.rejected[1]
