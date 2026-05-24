import pytest

from deck_builder.design_token_validator import (
    DesignTokenValidationError,
    DesignTokenValidator,
)


def valid_token(**overrides):
    token = {
        "namespace": "color",
        "name": "brand.primary",
        "type": "color",
        "value": "#FF6600",
        "unit": "hex",
        "source": "system_default",
        "description": "Primary brand color.",
    }
    token.update(overrides)
    return token


def test_valid_design_token_passes():
    result = DesignTokenValidator.from_file().validate(valid_token())
    assert result.valid is True
    assert result.errors == ()


def test_missing_required_name_fails():
    token = valid_token()
    del token["name"]

    result = DesignTokenValidator.from_file().validate(token)

    assert result.valid is False
    assert any("name" in error for error in result.errors)


def test_invalid_namespace_fails():
    token = valid_token(namespace="vibes")

    with pytest.raises(DesignTokenValidationError):
        DesignTokenValidator.from_file().assert_valid(token)


def test_invalid_type_fails():
    token = valid_token(type="gradient")

    result = DesignTokenValidator.from_file().validate(token)

    assert result.valid is False
    assert any("type" in error for error in result.errors)


def test_value_may_be_number():
    token = valid_token(
        namespace="spacing",
        name="spacing.large",
        type="spacing",
        value=32,
        unit="px",
    )

    result = DesignTokenValidator.from_file().validate(token)

    assert result.valid is True


def test_additional_property_fails():
    token = valid_token()
    token["random"] = "not allowed"

    result = DesignTokenValidator.from_file().validate(token)

    assert result.valid is False
    assert any("<root>" in error or "Additional properties" in error for error in result.errors)
