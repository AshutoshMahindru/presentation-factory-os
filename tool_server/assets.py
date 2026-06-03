from __future__ import annotations

from typing import Any

from deck_builder.asset_validator import AssetValidator


def validate_asset_payload(asset: dict[str, Any]) -> dict[str, Any]:
    result = AssetValidator().validate(asset)
    return {
        "valid": result.valid,
        "errors": list(result.errors),
        "warnings": list(result.warnings),
    }
