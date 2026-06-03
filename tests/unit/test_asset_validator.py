from deck_builder.asset_validator import AssetValidator
from tool_server.assets import validate_asset_payload


def valid_asset(**overrides):
    asset = {
        "asset_id": "asset_001",
        "kind": "logo",
        "provenance": "first_party",
        "width": 512,
        "height": 256,
        "safe_zone_ratio": 0.12,
    }
    asset.update(overrides)
    return asset


def test_asset_validator_accepts_logo_with_safe_zone():
    result = AssetValidator().validate(valid_asset())

    assert result.valid is True
    assert result.errors == ()


def test_asset_validator_rejects_missing_provenance_and_small_dimensions():
    result = AssetValidator().validate(valid_asset(provenance=None, width=64))

    assert result.valid is False
    assert "provenance is not allowed" in result.errors
    assert "asset dimensions must be at least 128px" in result.errors


def test_tool_server_asset_payload_wraps_validator_result():
    payload = validate_asset_payload(valid_asset(kind="photo", provenance="public_domain", brand_overlay=True))

    assert payload["valid"] is True
    assert payload["warnings"] == ["brand overlay on public-domain asset requires review"]
