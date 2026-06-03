from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping


class SlideFactoryError(ValueError):
    """Raised when slide factory scenario injection receives invalid input."""


class SlideFactory:
    """Builds slide payloads with validated financial scenario references."""

    def build_slide(
        self,
        slide: Mapping[str, Any],
        *,
        financial_cells: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] = (),
        scenario: str | None = None,
    ) -> dict[str, Any]:
        return inject_scenario_financial_refs(
            slide,
            financial_cells=financial_cells,
            scenario=scenario,
        )

    def create_slide(
        self,
        slide: Mapping[str, Any],
        *,
        financial_cells: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] = (),
        scenario: str | None = None,
    ) -> dict[str, Any]:
        return self.build_slide(
            slide,
            financial_cells=financial_cells,
            scenario=scenario,
        )

    def inject_scenario_financial_refs(
        self,
        slide: Mapping[str, Any],
        *,
        financial_cells: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
        scenario: str | None = None,
    ) -> dict[str, Any]:
        return inject_scenario_financial_refs(
            slide,
            financial_cells=financial_cells,
            scenario=scenario,
        )


def inject_scenario_financial_refs(
    slide: Mapping[str, Any],
    *,
    financial_cells: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
    scenario: str | None = None,
) -> dict[str, Any]:
    """Return a slide copy with validated scenario financial refs injected."""

    next_slide = deepcopy(dict(slide))
    content = next_slide.setdefault("content", {})
    if not isinstance(content, dict):
        raise SlideFactoryError("slide.content must be an object")

    existing_refs = [str(ref) for ref in content.get("financial_refs", []) or []]
    scenario_refs = [
        cell_ref
        for cell_ref, cell in _financial_cell_items(financial_cells)
        if _cell_matches_scenario(cell, scenario) and _cell_is_validated(cell)
    ]

    content["financial_refs"] = _stable_unique(existing_refs + sorted(scenario_refs))

    provenance = next_slide.setdefault("provenance", {})
    if isinstance(provenance, dict):
        provenance["financial_scenario"] = {
            "scenario": scenario,
            "financial_refs": tuple(content["financial_refs"]),
            "validation_status": "validated",
        }

    return next_slide


def build_slide(
    slide: Mapping[str, Any],
    *,
    financial_cells: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] = (),
    scenario: str | None = None,
) -> dict[str, Any]:
    return SlideFactory().build_slide(
        slide,
        financial_cells=financial_cells,
        scenario=scenario,
    )


def _financial_cell_items(
    financial_cells: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
) -> list[tuple[str, Mapping[str, Any]]]:
    if isinstance(financial_cells, Mapping):
        items = financial_cells.items()
    else:
        items = ((cell.get("cell_ref"), cell) for cell in financial_cells)

    out: list[tuple[str, Mapping[str, Any]]] = []
    for cell_ref, cell in items:
        if not cell_ref:
            continue
        out.append((str(cell_ref), cell))
    return out


def _cell_matches_scenario(cell: Mapping[str, Any], scenario: str | None) -> bool:
    if scenario is None:
        return True
    return str(cell.get("scenario", "") or "") == scenario


def _cell_is_validated(cell: Mapping[str, Any]) -> bool:
    return cell.get("validation_status", cell.get("status")) == "validated"


def _stable_unique(refs: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ref in refs:
        if ref not in seen:
            out.append(ref)
            seen.add(ref)
    return out
