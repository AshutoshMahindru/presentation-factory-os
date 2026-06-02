from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompiledCell:
    """One evaluated formula, ready to be persisted as a financial cell.

    Shape matches the input expected by FinancialModelValidator so the
    compiler's output can be passed straight into validation and (later)
    into the export pipeline.
    """

    project_id: str
    scenario: str
    cell_ref: str
    label: str
    value: float
    formula: str
    ingestion_source_type: str = "manual_compiler"
    parser_provenance: dict[str, str] | None = None
    artifact_status: str = "active"

    def to_validator_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "scenario": self.scenario,
            "cell_ref": self.cell_ref,
            "label": self.label,
            "value": self.value,
            "formula": self.formula,
            "ingestion_source_type": self.ingestion_source_type,
            "parser_provenance": self.parser_provenance or {},
            "artifact_status": self.artifact_status,
        }


@dataclass(frozen=True)
class CompilationResult:
    cells: tuple[CompiledCell, ...]
    warnings: tuple[str, ...] = ()


class CompilationError(ValueError):
    """Raised when a spec cannot be compiled (bad expression, cycle, etc.)."""


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------


# Whitelisted builtins. Anything else in an expression is rejected.
_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "pow": pow,
    "sqrt": math.sqrt,
    "log": math.log,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
}

# AST nodes we allow. Anything outside this set is rejected.
_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Call,
    ast.Tuple,
    ast.List,
)

PARSER_NAME = "pfos_spec_compiler"
PARSER_VERSION = "0.1.0"


class FinancialSpecCompiler:
    """Deterministic, LLM-free financial spec → cells compiler.

    The compiler:
      1. Parses each formula expression as a Python AST using only the
         safe node whitelist (no Name lookup at parse time, no eval).
      2. Extracts the set of variable names each formula depends on.
      3. Performs a topological sort over the dependency graph; cycles
         raise CompilationError.
      4. Evaluates each formula in order, with a namespace built from
         (a) the spec's constants, (b) the values of previously computed
         formulas. Evaluation uses a small sandboxed namespace — no
         access to Python builtins beyond the whitelist.

    Determinism: input order from the spec is preserved for tie-breaking
    in the topological sort. The compiler makes no I/O, no time, no
    random calls; given the same spec + project_id, output is identical.
    """

    def __init__(self) -> None:
        self._parser_name = PARSER_NAME
        self._parser_version = PARSER_VERSION

    def compile(
        self,
        spec: Mapping[str, Any],
        *,
        project_id: str,
    ) -> CompilationResult:
        scenario = str(spec.get("scenario", "base"))
        formulas_in = spec.get("formulas", [])
        constants_in = spec.get("constants", {})

        if not isinstance(formulas_in, list):
            raise CompilationError("spec.formulas must be a list")
        if not isinstance(constants_in, dict):
            raise CompilationError("spec.constants must be a dict")

        # Parse + index formulas.
        formulas: list[dict[str, Any]] = []
        names: set[str] = set()
        for index, raw in enumerate(formulas_in):
            if not isinstance(raw, dict):
                raise CompilationError(
                    f"formulas[{index}] must be an object"
                )
            name = str(raw.get("name", "")).strip()
            expression = str(raw.get("expression", "")).strip()
            label = str(raw.get("label", name))
            if not name:
                raise CompilationError(
                    f"formulas[{index}]: missing 'name'"
                )
            if not expression:
                raise CompilationError(
                    f"formulas[{index}] ({name}): missing 'expression'"
                )
            if name in names:
                raise CompilationError(
                    f"formulas[{index}]: duplicate formula name {name!r}"
                )
            names.add(name)
            # Build AST and extract dependencies.
            tree = self._parse_expression(expression, formula_name=name)
            deps = self._extract_dependencies(tree, formula_name=name)
            formulas.append(
                {
                    "name": name,
                    "expression": expression,
                    "label": label,
                    "deps": deps,
                    "tree": tree,
                }
            )

        # Validate constants: must be numeric.
        constants: dict[str, float] = {}
        for cname, cval in constants_in.items():
            try:
                constants[str(cname)] = float(cval)
            except (TypeError, ValueError):
                raise CompilationError(
                    f"constants.{cname}: must be numeric, got {cval!r}"
                )

        # Validate that formula names don't collide with constants.
        overlap = set(constants) & names
        if overlap:
            raise CompilationError(
                f"formula names overlap with constants: {sorted(overlap)}"
            )

        # Topological sort.
        order = self._topological_order(formulas, allowed_names=set(constants))

        # Evaluate.
        namespace: dict[str, float] = dict(constants)
        cells: list[CompiledCell] = []
        warnings: list[str] = []
        for fdef in order:
            try:
                value = self._evaluate(fdef["tree"], namespace, fdef["name"])
            except (ArithmeticError, ValueError, ZeroDivisionError) as exc:
                raise CompilationError(
                    f"formula {fdef['name']!r} evaluation failed: {exc}"
                ) from exc
            if not isinstance(value, (int, float)) or math.isnan(value):
                raise CompilationError(
                    f"formula {fdef['name']!r} produced non-finite value"
                )
            value_f = float(value)
            namespace[fdef["name"]] = value_f
            if math.isinf(value_f):
                warnings.append(
                    f"formula {fdef['name']!r} produced infinite value"
                )
            cells.append(
                CompiledCell(
                    project_id=project_id,
                    scenario=scenario,
                    cell_ref=fdef["name"],
                    label=fdef["label"],
                    value=value_f,
                    formula=fdef["expression"],
                    parser_provenance={
                        "parser_name": self._parser_name,
                        "parser_version": self._parser_version,
                    },
                )
            )

        return CompilationResult(
            cells=tuple(cells),
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_expression(
        self, expression: str, *, formula_name: str
    ) -> ast.Expression:
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise CompilationError(
                f"formula {formula_name!r}: invalid expression syntax: {exc}"
            ) from exc
        self._assert_safe(tree, formula_name=formula_name)
        return tree

    def _assert_safe(
        self, node: ast.AST, *, formula_name: str
    ) -> None:
        for child in ast.walk(node):
            if not isinstance(child, _ALLOWED_NODES):
                raise CompilationError(
                    f"formula {formula_name!r}: disallowed node "
                    f"{type(child).__name__}"
                )
            # Reject string/bytes constants — formulas are numeric.
            if isinstance(child, ast.Constant) and not isinstance(
                child.value, (int, float, bool)
            ):
                raise CompilationError(
                    f"formula {formula_name!r}: only numeric constants "
                    f"allowed, got {type(child.value).__name__}"
                )

    def _extract_dependencies(
        self, tree: ast.Expression, *, formula_name: str
    ) -> frozenset[str]:
        """Names referenced in the expression.

        We exclude names that appear as the function in a Call (those refer
        to whitelisted builtins, not to the formula/constant namespace).
        """
        # First pass: collect function names that are being called so we
        # don't mistake them for variable references.
        called_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
        # Second pass: collect variable references, skipping called names.
        deps: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id not in called_names:
                deps.add(node.id)
        return frozenset(deps)

    def _topological_order(
        self,
        formulas: list[dict[str, Any]],
        *,
        allowed_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        by_name: dict[str, dict[str, Any]] = {f["name"]: f for f in formulas}
        # Filter deps to those that are formulas or constants.
        known = set(by_name)
        if allowed_names:
            known |= allowed_names
        unknown: set[str] = set()
        filtered_deps: dict[str, frozenset[str]] = {}
        for f in formulas:
            keep = frozenset(d for d in f["deps"] if d in known)
            unknown |= f["deps"] - keep
            filtered_deps[f["name"]] = keep
        if unknown:
            raise CompilationError(
                f"unknown references: {sorted(unknown)}"
            )

        # Kahn's algorithm with input-order tie-breaking.
        # Only formula-to-formula edges count for in-degree; constants are
        # always pre-satisfied.
        in_degree: dict[str, int] = {
            name: len(deps & set(by_name)) for name, deps in filtered_deps.items()
        }
        ready: list[str] = sorted(
            n for n, d in in_degree.items() if d == 0
        )
        order: list[dict[str, Any]] = []
        # Track which deps of each name are satisfied.
        satisfied: dict[str, set[str]] = {n: set() for n in by_name}
        while ready:
            n = ready.pop(0)
            order.append(by_name[n])
            # For every formula that depends on n, decrement in-degree.
            for other, deps in filtered_deps.items():
                if n in deps and n not in satisfied[other]:
                    satisfied[other].add(n)
                    if len(satisfied[other]) == len(deps & set(by_name)):
                        ready.append(other)
            ready.sort()
        if len(order) != len(by_name):
            remaining = set(by_name) - {f["name"] for f in order}
            raise CompilationError(
                f"cyclic dependency among formulas: {sorted(remaining)}"
            )
        return order

    def _evaluate(
        self,
        tree: ast.Expression,
        namespace: dict[str, float],
        formula_name: str,
    ) -> float:
        # Build a minimal globals dict with only the safe builtins.
        safe_globals: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
        try:
            result = eval(  # noqa: S307 — sandboxed via AST whitelist
                compile(tree, f"<spec:{formula_name}>", "eval"),
                safe_globals,
                namespace,
            )
        except NameError as exc:
            raise CompilationError(
                f"formula {formula_name!r}: undefined name {exc}"
            ) from exc
        return result
