from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class SlideSchemaValidationError(Exception):
    """Raised when a slide job does not satisfy the slide job JSON Schema."""


@dataclass(frozen=True)
class SlideValidationResult:
    valid: bool
    errors: tuple[str, ...]


class SlideSchemaValidator:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema
        self.validator = Draft202012Validator(schema)

    @classmethod
    def from_file(
        cls,
        path: str | Path = "docs/06_SlideJobDefinition.schema.json",
    ) -> "SlideSchemaValidator":
        schema_path = Path(path)
        if not schema_path.exists():
            raise FileNotFoundError(f"Slide schema not found: {schema_path}")
        return cls(json.loads(schema_path.read_text()))

    def validate(self, payload: dict[str, Any]) -> SlideValidationResult:
        errors = sorted(self.validator.iter_errors(payload), key=lambda error: list(error.path))
        messages = tuple(self._format_error(error) for error in errors)
        return SlideValidationResult(valid=not messages, errors=messages)

    def assert_valid(self, payload: dict[str, Any]) -> None:
        result = self.validate(payload)
        if not result.valid:
            raise SlideSchemaValidationError("; ".join(result.errors))

    @staticmethod
    def _format_error(error: Any) -> str:
        path = ".".join(str(part) for part in error.path)
        if not path:
            path = "<root>"
        return f"{path}: {error.message}"
