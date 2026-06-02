from __future__ import annotations

import math

import pytest

from financial_model.spec_compiler import (
    CompilationError,
    CompiledCell,
    CompilationResult,
    FinancialSpecCompiler,
    PARSER_NAME,
    PARSER_VERSION,
)
from financial_model.validator import FinancialModelValidator


def _spec(formulas, *, scenario="base", constants=None):
    out = {"scenario": scenario, "formulas": formulas}
    if constants is not None:
        out["constants"] = constants
    return out


# ---------------------------------------------------------------------------
# Trivial arithmetic
# ---------------------------------------------------------------------------


def test_compile_constant_only_formula() -> None:
    compiler = FinancialSpecCompiler()
    result = compiler.compile(
        _spec(
            [{"name": "X", "expression": "42", "label": "the answer"}],
            constants={},
        ),
        project_id="proj-1",
    )
    assert len(result.cells) == 1
    cell = result.cells[0]
    assert cell.cell_ref == "X"
    assert cell.value == 42.0
    assert cell.scenario == "base"
    assert cell.label == "the answer"
    assert cell.parser_provenance == {
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
    }


def test_compile_with_constants() -> None:
    compiler = FinancialSpecCompiler()
    result = compiler.compile(
        _spec(
            [
                {"name": "Doubled", "expression": "rate * 2", "label": ""},
            ],
            constants={"rate": 7.5},
        ),
        project_id="proj-1",
    )
    assert result.cells[0].value == 15.0


def test_compile_with_dependencies() -> None:
    compiler = FinancialSpecCompiler()
    result = compiler.compile(
        _spec(
            [
                {"name": "A", "expression": "10", "label": ""},
                {"name": "B", "expression": "A * 2", "label": ""},
                {"name": "C", "expression": "A + B", "label": ""},
            ],
        ),
        project_id="proj-1",
    )
    assert [c.cell_ref for c in result.cells] == ["A", "B", "C"]
    assert [c.value for c in result.cells] == [10.0, 20.0, 30.0]


def test_compile_multi_level_dependency_chain() -> None:
    """Diamond: D depends on B and C, both depend on A."""
    compiler = FinancialSpecCompiler()
    result = compiler.compile(
        _spec(
            [
                {"name": "A", "expression": "5", "label": ""},
                {"name": "B", "expression": "A + 1", "label": ""},
                {"name": "C", "expression": "A + 2", "label": ""},
                {"name": "D", "expression": "B + C", "label": ""},
            ],
        ),
        project_id="proj-1",
    )
    assert [c.value for c in result.cells] == [5.0, 6.0, 7.0, 13.0]


# ---------------------------------------------------------------------------
# Scenario + project_id propagation
# ---------------------------------------------------------------------------


def test_compile_propagates_project_id_and_scenario() -> None:
    compiler = FinancialSpecCompiler()
    result = compiler.compile(
        _spec([{"name": "X", "expression": "1", "label": "lbl"}], scenario="bull"),
        project_id="proj-99",
    )
    c = result.cells[0]
    assert c.project_id == "proj-99"
    assert c.scenario == "bull"
    assert c.label == "lbl"


# ---------------------------------------------------------------------------
# Builtin functions (whitelisted)
# ---------------------------------------------------------------------------


def test_compile_uses_whitelisted_builtin_sqrt() -> None:
    compiler = FinancialSpecCompiler()
    result = compiler.compile(
        _spec([{"name": "Root", "expression": "sqrt(16)", "label": ""}]),
        project_id="proj-1",
    )
    assert result.cells[0].value == 4.0


def test_compile_uses_max_for_aggregation() -> None:
    compiler = FinancialSpecCompiler()
    result = compiler.compile(
        _spec(
            [
                {"name": "A", "expression": "1", "label": ""},
                {"name": "B", "expression": "5", "label": ""},
                {"name": "Best", "expression": "max(A, B, 3)", "label": ""},
            ],
        ),
        project_id="proj-1",
    )
    assert result.cells[-1].value == 5.0


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_compile_rejects_missing_formula_name() -> None:
    compiler = FinancialSpecCompiler()
    with pytest.raises(CompilationError, match="missing 'name'"):
        compiler.compile(
            _spec([{"expression": "1", "label": ""}]),
            project_id="proj-1",
        )


def test_compile_rejects_missing_expression() -> None:
    compiler = FinancialSpecCompiler()
    with pytest.raises(CompilationError, match="missing 'expression'"):
        compiler.compile(
            _spec([{"name": "X", "label": ""}]),
            project_id="proj-1",
        )


def test_compile_rejects_duplicate_formula_name() -> None:
    compiler = FinancialSpecCompiler()
    with pytest.raises(CompilationError, match="duplicate formula name"):
        compiler.compile(
            _spec(
                [
                    {"name": "X", "expression": "1", "label": ""},
                    {"name": "X", "expression": "2", "label": ""},
                ],
            ),
            project_id="proj-1",
        )


def test_compile_rejects_non_numeric_constant() -> None:
    compiler = FinancialSpecCompiler()
    with pytest.raises(CompilationError, match="must be numeric"):
        compiler.compile(
            _spec(
                [{"name": "X", "expression": "rate * 2", "label": ""}],
                constants={"rate": "fast"},
            ),
            project_id="proj-1",
        )


def test_compile_rejects_unknown_reference() -> None:
    compiler = FinancialSpecCompiler()
    with pytest.raises(CompilationError, match="unknown references"):
        compiler.compile(
            _spec([{"name": "X", "expression": "ghost * 2", "label": ""}]),
            project_id="proj-1",
        )


def test_compile_rejects_cycle() -> None:
    compiler = FinancialSpecCompiler()
    with pytest.raises(CompilationError, match="cyclic dependency"):
        compiler.compile(
            _spec(
                [
                    {"name": "A", "expression": "B + 1", "label": ""},
                    {"name": "B", "expression": "A + 1", "label": ""},
                ],
            ),
            project_id="proj-1",
        )


def test_compile_rejects_invalid_syntax() -> None:
    compiler = FinancialSpecCompiler()
    with pytest.raises(CompilationError, match="invalid expression syntax"):
        compiler.compile(
            _spec([{"name": "X", "expression": "1 +", "label": ""}]),
            project_id="proj-1",
        )


def test_compile_rejects_disallowed_node_attribute_access() -> None:
    """No attribute access allowed — only arithmetic + whitelist."""
    compiler = FinancialSpecCompiler()
    with pytest.raises(CompilationError, match="disallowed node"):
        compiler.compile(
            _spec(
                [{"name": "X", "expression": "(1).__class__", "label": ""}]
            ),
            project_id="proj-1",
        )


def test_compile_rejects_string_constant() -> None:
    """Only numeric constants are allowed in expressions."""
    compiler = FinancialSpecCompiler()
    with pytest.raises(CompilationError, match="only numeric constants"):
        compiler.compile(
            _spec(
                [{"name": "X", "expression": "'hello'", "label": ""}]
            ),
            project_id="proj-1",
        )


def test_compile_rejects_undefined_name_in_expression() -> None:
    """A name that isn't a formula or constant is rejected at topo sort."""
    compiler = FinancialSpecCompiler()
    with pytest.raises(CompilationError, match="unknown references"):
        compiler.compile(
            _spec(
                [{"name": "X", "expression": "nonexistent_thing", "label": ""}]
            ),
            project_id="proj-1",
        )


def test_compile_rejects_formula_name_clash_with_constant() -> None:
    compiler = FinancialSpecCompiler()
    with pytest.raises(CompilationError, match="overlap with constants"):
        compiler.compile(
            _spec(
                [{"name": "X", "expression": "1", "label": ""}],
                constants={"X": 5},
            ),
            project_id="proj-1",
        )


def test_compile_rejects_zero_division() -> None:
    compiler = FinancialSpecCompiler()
    with pytest.raises(CompilationError, match="evaluation failed"):
        compiler.compile(
            _spec(
                [{"name": "X", "expression": "1/0", "label": ""}],
            ),
            project_id="proj-1",
        )


# ---------------------------------------------------------------------------
# Output shape — cell dicts must be validator-compatible
# ---------------------------------------------------------------------------


def test_compiled_cells_pass_validator() -> None:
    """End-to-end: compiler output must validate cleanly."""
    compiler = FinancialSpecCompiler()
    spec = _spec(
        [
            {"name": "Revenue", "expression": "1000 * (1 + growth_rate)", "label": "Revenue"},
            {"name": "NetIncome", "expression": "Revenue - cost", "label": "Net"},
        ],
        constants={"growth_rate": 0.15, "cost": 500},
    )
    result = compiler.compile(spec, project_id="proj-1")

    # Pass through the existing validator
    cells = [c.to_validator_dict() for c in result.cells]
    validator = FinancialModelValidator()
    validation = validator.validate_cells(cells)
    assert validation.valid is True, validation.errors

    # Spot-check the values
    by_ref = {c["cell_ref"]: c for c in cells}
    assert by_ref["Revenue"]["value"] == 1150.0
    assert by_ref["NetIncome"]["value"] == 650.0
    assert by_ref["Revenue"]["parser_provenance"]["parser_name"] == PARSER_NAME


def test_compile_is_deterministic() -> None:
    """Same input must produce byte-identical output."""
    compiler = FinancialSpecCompiler()
    spec = _spec(
        [
            {"name": "A", "expression": "1 + 1", "label": ""},
            {"name": "B", "expression": "A * 3", "label": ""},
        ],
    )
    r1 = compiler.compile(spec, project_id="proj-1")
    r2 = compiler.compile(spec, project_id="proj-1")
    # Compare by value tuples
    v1 = [(c.cell_ref, c.value) for c in r1.cells]
    v2 = [(c.cell_ref, c.value) for c in r2.cells]
    assert v1 == v2
