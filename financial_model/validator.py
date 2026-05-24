from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any


class FinancialValidationError(Exception):
    """Raised when financial cells fail deterministic validation."""


@dataclass(frozen=True)
class FinancialValidationResult:
    valid: bool
    errors: tuple[str, ...]


class FinancialModelValidator:
    ALLOWED_PARSERS = {"openpyxl_with_formulas_lib"}
    ALLOWED_ARTIFACT_STATUSES = {"active", "stale_due_to_retreat", "archived", "blocked"}

    REQUIRED_FIELDS = {
        "project_id",
        "scenario",
        "cell_ref",
        "label",
        "value",
        "formula",
    }

    def validate_cells(self, cells: list[dict[str, Any]]) -> FinancialValidationResult:
        errors: list[str] = []
        seen_keys: set[tuple[str, str, str]] = set()

        for index, cell in enumerate(cells):
            prefix = f"cell[{index}]"

            self._check_required_fields(prefix, cell, errors)
            self._check_formula(prefix, cell, errors)
            self._check_value(prefix, cell, errors)
            self._check_composite_uniqueness(prefix, cell, seen_keys, errors)
            self._check_parser_provenance(prefix, cell, errors)
            self._check_artifact_status(prefix, cell, errors)

        return FinancialValidationResult(valid=not errors, errors=tuple(errors))

    def assert_valid_cells(self, cells: list[dict[str, Any]]) -> None:
        result = self.validate_cells(cells)
        if not result.valid:
            raise FinancialValidationError("; ".join(result.errors))

    def _check_required_fields(self, prefix: str, cell: dict[str, Any], errors: list[str]) -> None:
        for field in sorted(self.REQUIRED_FIELDS):
            if field not in cell or cell[field] in (None, ""):
                errors.append(f"{prefix}: missing required field {field}")

    def _check_formula(self, prefix: str, cell: dict[str, Any], errors: list[str]) -> None:
        formula = str(cell.get("formula", "") or "").strip()
        if not formula:
            errors.append(f"{prefix}: formula must not be blank")

    def _check_value(self, prefix: str, cell: dict[str, Any], errors: list[str]) -> None:
        value = cell.get("value")
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            errors.append(f"{prefix}: value must be numeric")
            return

        if not isfinite(numeric_value):
            errors.append(f"{prefix}: value must be finite")

    def _check_composite_uniqueness(
        self,
        prefix: str,
        cell: dict[str, Any],
        seen_keys: set[tuple[str, str, str]],
        errors: list[str],
    ) -> None:
        project_id = cell.get("project_id")
        scenario = cell.get("scenario")
        cell_ref = cell.get("cell_ref")

        if not project_id or not scenario or not cell_ref:
            return

        key = (str(project_id), str(scenario), str(cell_ref))
        if key in seen_keys:
            errors.append(f"{prefix}: duplicate financial cell identity {key}")
        seen_keys.add(key)

    def _check_parser_provenance(self, prefix: str, cell: dict[str, Any], errors: list[str]) -> None:
        source_type = cell.get("ingestion_source_type", "manual_entry")
        provenance = cell.get("parser_provenance") or {}

        if source_type == "excel_xlsx":
            if not isinstance(provenance, dict) or not provenance:
                errors.append(f"{prefix}: excel_xlsx cells require parser_provenance")
                return

            for required in ("parser_name", "parser_version"):
                if not provenance.get(required):
                    errors.append(f"{prefix}: parser_provenance missing {required}")

            parser_name = provenance.get("parser_name")
            if parser_name and parser_name not in self.ALLOWED_PARSERS:
                errors.append(f"{prefix}: parser_name {parser_name} is not allow-listed")

    def _check_artifact_status(self, prefix: str, cell: dict[str, Any], errors: list[str]) -> None:
        status = cell.get("artifact_status", "active")
        if status not in self.ALLOWED_ARTIFACT_STATUSES:
            errors.append(f"{prefix}: invalid artifact_status {status}")
