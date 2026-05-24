from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class DesignTokenValidationError(Exception):
    """Raised when a design token payload does not satisfy the design token schema."""


@dataclass(frozen=True)
class DesignTokenValidationResult:
    valid: bool
    errors: tuple[str, ...]


class DesignTokenValidator:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema
        self.validator = Draft202012Validator(schema)

    @classmethod
    def from_file(
        cls,
        path: str | Path = "docs/21_DesignTokens.schema.json",
    ) -> "DesignTokenValidator":
        schema_path = Path(path)
        if not schema_path.exists():
            raise FileNotFoundError(f"Design token schema not found: {schema_path}")
        return cls(json.loads(schema_path.read_text()))

    def validate(self, payload: dict[str, Any]) -> DesignTokenValidationResult:
        errors = sorted(self.validator.iter_errors(payload), key=lambda error: list(error.path))
        messages = tuple(self._format_error(error) for error in errors)
        return DesignTokenValidationResult(valid=not messages, errors=messages)

    def assert_valid(self, payload: dict[str, Any]) -> None:
        result = self.validate(payload)
        if not result.valid:
            raise DesignTokenValidationError("; ".join(result.errors))

    @staticmethod
    def _format_error(error: Any) -> str:
        path = ".".join(str(part) for part in error.path)
        if not path:
            path = "<root>"
        return f"{path}: {error.message}"
