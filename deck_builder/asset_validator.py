from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssetValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


class AssetValidator:
    ALLOWED_KINDS = {"logo", "photo", "icon", "chart", "diagram"}
    ALLOWED_PROVENANCE = {"licensed", "first_party", "generated", "public_domain"}

    def validate(self, asset: dict[str, Any]) -> AssetValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        asset_id = asset.get("asset_id")
        if not asset_id:
            errors.append("asset_id is required")
        if asset.get("kind") not in self.ALLOWED_KINDS:
            errors.append("kind is not allowed")
        if asset.get("provenance") not in self.ALLOWED_PROVENANCE:
            errors.append("provenance is not allowed")

        width = int(asset.get("width", 0) or 0)
        height = int(asset.get("height", 0) or 0)
        if width < 128 or height < 128:
            errors.append("asset dimensions must be at least 128px")

        if asset.get("kind") == "logo":
            safe_zone = float(asset.get("safe_zone_ratio", 0) or 0)
            if safe_zone < 0.08:
                errors.append("logo safe_zone_ratio must be at least 0.08")

        if asset.get("brand_overlay") and asset.get("provenance") == "public_domain":
            warnings.append("brand overlay on public-domain asset requires review")

        return AssetValidationResult(valid=not errors, errors=tuple(errors), warnings=tuple(warnings))
