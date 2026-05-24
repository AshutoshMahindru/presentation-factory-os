import pytest

from financial_model.validator import FinancialModelValidator, FinancialValidationError


def valid_cell(**overrides):
    cell = {
        "project_id": "project_001",
        "scenario": "base",
        "cell_ref": "FM!CM_M18_BASE",
        "label": "Contribution margin month 18",
        "value": 0.38,
        "formula": "=Revenue-Cost",
        "ingestion_source_type": "manual_entry",
        "parser_provenance": {},
        "artifact_status": "active",
    }
    cell.update(overrides)
    return cell


def test_valid_manual_cell_passes():
    result = FinancialModelValidator().validate_cells([valid_cell()])
    assert result.valid is True
    assert result.errors == ()


def test_missing_required_field_fails():
    cell = valid_cell()
    del cell["formula"]

    result = FinancialModelValidator().validate_cells([cell])

    assert result.valid is False
    assert any("formula" in error for error in result.errors)


def test_blank_formula_fails():
    cell = valid_cell(formula=" ")

    with pytest.raises(FinancialValidationError):
        FinancialModelValidator().assert_valid_cells([cell])


def test_non_numeric_value_fails():
    cell = valid_cell(value="not-a-number")

    result = FinancialModelValidator().validate_cells([cell])

    assert result.valid is False
    assert any("value must be numeric" in error for error in result.errors)


def test_duplicate_cell_identity_fails():
    cells = [valid_cell(), valid_cell()]

    result = FinancialModelValidator().validate_cells(cells)

    assert result.valid is False
    assert any("duplicate financial cell identity" in error for error in result.errors)


def test_excel_cell_requires_parser_provenance():
    cell = valid_cell(ingestion_source_type="excel_xlsx", parser_provenance={})

    result = FinancialModelValidator().validate_cells([cell])

    assert result.valid is False
    assert any("parser_provenance" in error for error in result.errors)


def test_excel_cell_with_allowlisted_parser_passes():
    cell = valid_cell(
        ingestion_source_type="excel_xlsx",
        parser_provenance={
            "parser_name": "openpyxl_with_formulas_lib",
            "parser_version": "0.1.0",
        },
    )

    result = FinancialModelValidator().validate_cells([cell])

    assert result.valid is True


def test_excel_cell_with_non_allowlisted_parser_fails():
    cell = valid_cell(
        ingestion_source_type="excel_xlsx",
        parser_provenance={
            "parser_name": "llm_guessed_parser",
            "parser_version": "0.1.0",
        },
    )

    result = FinancialModelValidator().validate_cells([cell])

    assert result.valid is False
    assert any("not allow-listed" in error for error in result.errors)


def test_invalid_artifact_status_fails():
    cell = valid_cell(artifact_status="final_final_v7")

    result = FinancialModelValidator().validate_cells([cell])

    assert result.valid is False
    assert any("artifact_status" in error for error in result.errors)
