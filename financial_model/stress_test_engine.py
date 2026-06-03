from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from numbers import Real
from typing import Any, Iterable, Mapping


ALLOWED_DEPENDENCY_TYPES = frozenset(
    {"sensitivity", "downside", "upside", "base_clone", "manual_override"}
)


class StressTestValidationError(ValueError):
    """Raised when a stress scenario cannot be tied to a declared dependency."""


@dataclass(frozen=True)
class ScenarioDependency:
    project_id: str
    scenario: str
    depends_on_scenario: str
    dependency_type: str
    rationale: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class StressTestResult:
    project_id: str
    scenario: str
    depends_on_scenario: str
    dependency_type: str
    stressed_cells: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]
    warnings: tuple[str, ...] = ()

    def to_financial_cells(self) -> list[dict[str, Any]]:
        return [dict(cell) for cell in self.stressed_cells]


class StressTestEngine:
    """Small deterministic stress-test lane for declared financial scenarios."""

    allowed_dependency_types = ALLOWED_DEPENDENCY_TYPES

    def validate_dependency(
        self, dependency: ScenarioDependency | Mapping[str, Any]
    ) -> ScenarioDependency:
        dep = self._coerce_dependency(dependency)
        errors: list[str] = []

        if not dep.project_id:
            errors.append("project_id is required")
        if not dep.scenario:
            errors.append("scenario is required")
        if not dep.depends_on_scenario:
            errors.append("depends_on_scenario is required")
        if dep.scenario and dep.scenario == dep.depends_on_scenario:
            errors.append("scenario dependencies cannot point to themselves")
        if dep.dependency_type not in self.allowed_dependency_types:
            errors.append(f"unsupported dependency_type {dep.dependency_type!r}")

        if errors:
            raise StressTestValidationError("; ".join(errors))
        return dep

    def validate_dependencies(
        self, dependencies: Iterable[ScenarioDependency | Mapping[str, Any]]
    ) -> tuple[ScenarioDependency, ...]:
        return tuple(self.validate_dependency(dependency) for dependency in dependencies)

    def build_metadata(
        self,
        dependency: ScenarioDependency | Mapping[str, Any],
        *,
        cell_refs: Iterable[str] = (),
        shocks: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        dep = self.validate_dependency(dependency)
        return {
            "engine": "pfos_stress_test_engine",
            "deterministic": True,
            "project_id": dep.project_id,
            "scenario": dep.scenario,
            "depends_on_scenario": dep.depends_on_scenario,
            "dependency_type": dep.dependency_type,
            "rationale": dep.rationale,
            "cell_refs": tuple(sorted(str(ref) for ref in cell_refs)),
            "shocks": dict(sorted((shocks or {}).items())),
        }

    def stress_cells(
        self,
        cells: Iterable[Any],
        dependency: ScenarioDependency | Mapping[str, Any],
        *,
        shocks: Mapping[str, Any] | None = None,
    ) -> StressTestResult:
        dep = self.validate_dependency(dependency)
        shock_map = dict(shocks or {})
        stressed: list[dict[str, Any]] = []
        warnings: list[str] = []

        for raw_cell in cells:
            cell = self._coerce_cell(raw_cell)
            source_scenario = str(cell.get("scenario", "") or "")
            if source_scenario and source_scenario != dep.depends_on_scenario:
                continue

            cell_ref = str(cell.get("cell_ref", "") or "")
            if not cell_ref:
                warnings.append("skipped cell without cell_ref")
                continue

            value = self._coerce_numeric_value(cell)
            shock = shock_map.get(cell_ref, shock_map.get(cell.get("label")))
            stressed_value = self._apply_shock(value, shock)

            next_cell = dict(cell)
            next_cell["project_id"] = dep.project_id
            next_cell["scenario"] = dep.scenario
            next_cell["value"] = stressed_value
            next_cell.setdefault("validation_status", "validated")
            next_cell["stress_test_metadata"] = self.build_metadata(
                dep,
                cell_refs=(cell_ref,),
                shocks={cell_ref: shock} if shock is not None else {},
            )
            stressed.append(next_cell)

        metadata = self.build_metadata(
            dep,
            cell_refs=(cell.get("cell_ref", "") for cell in stressed),
            shocks=shock_map,
        )
        return StressTestResult(
            project_id=dep.project_id,
            scenario=dep.scenario,
            depends_on_scenario=dep.depends_on_scenario,
            dependency_type=dep.dependency_type,
            stressed_cells=tuple(stressed),
            metadata=metadata,
            warnings=tuple(warnings),
        )

    def run(
        self,
        cells: Iterable[Any],
        dependency: ScenarioDependency | Mapping[str, Any],
        *,
        shocks: Mapping[str, Any] | None = None,
    ) -> StressTestResult:
        return self.stress_cells(cells, dependency, shocks=shocks)

    @staticmethod
    def _coerce_dependency(
        dependency: ScenarioDependency | Mapping[str, Any]
    ) -> ScenarioDependency:
        if isinstance(dependency, ScenarioDependency):
            return dependency
        return ScenarioDependency(
            project_id=str(dependency.get("project_id", "") or ""),
            scenario=str(dependency.get("scenario", "") or ""),
            depends_on_scenario=str(dependency.get("depends_on_scenario", "") or ""),
            dependency_type=str(dependency.get("dependency_type", "") or ""),
            rationale=str(dependency.get("rationale", "") or ""),
        )

    @staticmethod
    def _coerce_cell(raw_cell: Any) -> dict[str, Any]:
        if hasattr(raw_cell, "to_validator_dict"):
            return dict(raw_cell.to_validator_dict())
        if isinstance(raw_cell, Mapping):
            return dict(raw_cell)
        if is_dataclass(raw_cell):
            return asdict(raw_cell)
        raise StressTestValidationError(f"unsupported financial cell {raw_cell!r}")

    @staticmethod
    def _coerce_numeric_value(cell: Mapping[str, Any]) -> float:
        try:
            return float(cell.get("value"))
        except (TypeError, ValueError) as exc:
            cell_ref = cell.get("cell_ref", "<unknown>")
            raise StressTestValidationError(
                f"{cell_ref}: value must be numeric for stress testing"
            ) from exc

    @staticmethod
    def _apply_shock(value: float, shock: Any) -> float:
        if shock is None:
            return value
        if isinstance(shock, Real):
            return value * (1.0 + float(shock))
        if isinstance(shock, Mapping):
            if "value" in shock:
                return float(shock["value"])
            if "override" in shock:
                return float(shock["override"])
            if "multiplier" in shock:
                return value * float(shock["multiplier"])
            if "factor" in shock:
                return value * float(shock["factor"])
            for key in ("percentage_delta", "percent_delta", "delta_pct", "shock_pct"):
                if key in shock:
                    return value * (1.0 + float(shock[key]))
            for key in ("additive", "absolute_delta", "delta"):
                if key in shock:
                    return value + float(shock[key])
        raise StressTestValidationError(f"unsupported stress shock {shock!r}")


def build_stress_test_metadata(
    dependency: ScenarioDependency | Mapping[str, Any],
    *,
    cell_refs: Iterable[str] = (),
    shocks: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return StressTestEngine().build_metadata(
        dependency,
        cell_refs=cell_refs,
        shocks=shocks,
    )


def run_stress_test(
    cells: Iterable[Any],
    dependency: ScenarioDependency | Mapping[str, Any],
    *,
    shocks: Mapping[str, Any] | None = None,
) -> StressTestResult:
    return StressTestEngine().stress_cells(cells, dependency, shocks=shocks)
