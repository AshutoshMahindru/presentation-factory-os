from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping


class SlideFactoryError(ValueError):
    """Raised when slide factory scenario injection receives invalid input."""


VALID_MATERIALITY = {"high", "medium", "low"}
PILLAR_JOB_TYPES = {
    "claim": "compare_competitive_position",
    "data": "establish_market_size",
    "financial": "explain_unit_economics",
    "narrative": "define_strategic_path",
    "objection": "address_risk",
}
PILLAR_MATERIALITY = {
    "claim": "medium",
    "data": "high",
    "financial": "high",
    "narrative": "low",
    "objection": "medium",
}


class SlideFactory:
    """Builds deterministic slide payloads from thesis pillar context."""

    def build_slide_jobs_from_pillars(
        self,
        pillars: Iterable[Mapping[str, Any]],
        *,
        source_refs_by_pillar: Mapping[str, Iterable[str]] | None = None,
        financial_cells_by_pillar: Mapping[
            str,
            Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
        ]
        | None = None,
        scenario: str | None = None,
    ) -> list[dict[str, Any]]:
        return build_slide_jobs_from_pillars(
            pillars,
            source_refs_by_pillar=source_refs_by_pillar,
            financial_cells_by_pillar=financial_cells_by_pillar,
            scenario=scenario,
        )

    def build_slide(
        self,
        slide: Mapping[str, Any],
        *,
        source_refs: Iterable[str] = (),
        financial_refs: Iterable[str] = (),
        financial_cells: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] = (),
        scenario: str | None = None,
    ) -> dict[str, Any]:
        return build_slide(
            slide,
            source_refs=source_refs,
            financial_refs=financial_refs,
            financial_cells=financial_cells,
            scenario=scenario,
        )

    def create_slide(
        self,
        slide: Mapping[str, Any],
        *,
        source_refs: Iterable[str] = (),
        financial_refs: Iterable[str] = (),
        financial_cells: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] = (),
        scenario: str | None = None,
    ) -> dict[str, Any]:
        return self.build_slide(
            slide,
            source_refs=source_refs,
            financial_refs=financial_refs,
            financial_cells=financial_cells,
            scenario=scenario,
        )

    def inject_auto_refs(
        self,
        slide: Mapping[str, Any],
        *,
        source_refs: Iterable[str] = (),
        financial_refs: Iterable[str] = (),
        financial_cells: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] = (),
        scenario: str | None = None,
    ) -> dict[str, Any]:
        return inject_auto_refs(
            slide,
            source_refs=source_refs,
            financial_refs=financial_refs,
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


def build_slide_jobs_from_pillars(
    pillars: Iterable[Mapping[str, Any]],
    *,
    source_refs_by_pillar: Mapping[str, Iterable[str]] | None = None,
    financial_cells_by_pillar: Mapping[
        str,
        Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
    ]
    | None = None,
    scenario: str | None = None,
) -> list[dict[str, Any]]:
    """Map thesis pillars into deterministic slide-job payloads."""

    source_refs_by_pillar = source_refs_by_pillar or {}
    financial_cells_by_pillar = financial_cells_by_pillar or {}
    slides: list[dict[str, Any]] = []

    for ordinal, pillar in enumerate(_ordered_pillars(pillars), start=1):
        pillar_id = _pillar_id(pillar, ordinal)
        pillar_type = str(pillar.get("pillar_type") or pillar.get("type") or "claim")
        if pillar_type not in PILLAR_JOB_TYPES:
            raise SlideFactoryError(f"Unsupported pillar_type: {pillar_type}")

        statement = _pillar_statement(pillar)
        source_refs = _stable_unique(
            list(source_refs_by_pillar.get(pillar_id, ()))
            + list(pillar.get("source_refs", []) or [])
            + list(pillar.get("source_ids", []) or [])
        )
        required_evidence = source_refs or [f"source_required_for_{pillar_id}"]
        slide = {
            "slide_id": f"slide_{ordinal:03d}",
            "job": {
                "type": PILLAR_JOB_TYPES[pillar_type],
                "required_evidence": list(required_evidence),
                "objective": statement,
                "phase": "narrative" if pillar_type != "financial" else "financial_model",
            },
            "content": {
                "headline": _headline_from_statement(statement),
                "body": statement,
                "chart_id": None,
                "evidence_refs": list(source_refs),
                "financial_refs": [],
            },
            "visual_quality": "code_generated",
            "materiality": derive_materiality(pillar),
            "narrative_arc": _narrative_arc_for_pillar(pillar_type),
            "provenance": {
                "pillar": {
                    "pillar_id": pillar_id,
                    "pillar_type": pillar_type,
                    "pillar_index": _pillar_index(pillar, ordinal - 1),
                }
            },
        }
        slide = inject_auto_refs(
            slide,
            source_refs=source_refs,
            financial_cells=financial_cells_by_pillar.get(pillar_id, ()),
            scenario=scenario,
        )
        slides.append(slide)

    return slides


def derive_materiality(pillar: Mapping[str, Any]) -> str:
    """Return explicit valid materiality or a deterministic type-based default."""

    materiality = str(pillar.get("materiality", "") or "")
    if materiality in VALID_MATERIALITY:
        return materiality

    pillar_type = str(pillar.get("pillar_type") or pillar.get("type") or "claim")
    return PILLAR_MATERIALITY.get(pillar_type, "medium")


def inject_auto_refs(
    slide: Mapping[str, Any],
    *,
    source_refs: Iterable[str] = (),
    financial_refs: Iterable[str] = (),
    financial_cells: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] = (),
    scenario: str | None = None,
) -> dict[str, Any]:
    """Inject source refs and validated financial refs into a slide copy."""

    next_slide = deepcopy(dict(slide))
    content = next_slide.setdefault("content", {})
    if not isinstance(content, dict):
        raise SlideFactoryError("slide.content must be an object")

    job = next_slide.setdefault("job", {})
    if not isinstance(job, dict):
        raise SlideFactoryError("slide.job must be an object")

    normalized_source_refs = sorted(_stable_unique(str(ref) for ref in source_refs if ref))
    existing_evidence_refs = [str(ref) for ref in content.get("evidence_refs", []) or []]
    existing_required_evidence = [str(ref) for ref in job.get("required_evidence", []) or []]
    content["evidence_refs"] = _stable_unique(existing_evidence_refs + normalized_source_refs)
    job["required_evidence"] = _stable_unique(existing_required_evidence + normalized_source_refs)

    validated_financial_refs = [
        cell_ref
        for cell_ref, cell in _financial_cell_items(financial_cells)
        if _cell_matches_scenario(cell, scenario) and _cell_is_validated(cell)
    ]
    existing_financial_refs = [str(ref) for ref in content.get("financial_refs", []) or []]
    content["financial_refs"] = _stable_unique(
        existing_financial_refs
        + sorted(str(ref) for ref in financial_refs if ref)
        + sorted(validated_financial_refs)
    )

    provenance = next_slide.setdefault("provenance", {})
    if isinstance(provenance, dict):
        provenance["auto_refs"] = {
            "evidence_refs": tuple(content["evidence_refs"]),
            "financial_refs": tuple(content["financial_refs"]),
        }

    return next_slide


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
    source_refs: Iterable[str] = (),
    financial_refs: Iterable[str] = (),
    financial_cells: Iterable[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] = (),
    scenario: str | None = None,
) -> dict[str, Any]:
    slide_with_refs = inject_auto_refs(
        slide,
        source_refs=source_refs,
        financial_refs=financial_refs,
        financial_cells=financial_cells,
        scenario=scenario,
    )
    return inject_scenario_financial_refs(
        slide_with_refs,
        financial_cells=financial_cells,
        scenario=scenario,
    )


def _ordered_pillars(pillars: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        list(pillars),
        key=lambda pillar: (
            _pillar_index(pillar, 0),
            str(pillar.get("id") or pillar.get("pillar_id") or ""),
        ),
    )


def _pillar_id(pillar: Mapping[str, Any], ordinal: int) -> str:
    return str(pillar.get("id") or pillar.get("pillar_id") or f"pillar_{ordinal:03d}")


def _pillar_index(pillar: Mapping[str, Any], default: int) -> int:
    try:
        return int(pillar.get("pillar_index", default))
    except (TypeError, ValueError):
        return default


def _pillar_statement(pillar: Mapping[str, Any]) -> str:
    statement = str(pillar.get("statement") or pillar.get("summary") or "").strip()
    if not statement:
        raise SlideFactoryError("pillar.statement is required")
    return statement


def _headline_from_statement(statement: str) -> str:
    return statement if len(statement) <= 120 else f"{statement[:117].rstrip()}..."


def _narrative_arc_for_pillar(pillar_type: str) -> str:
    if pillar_type == "objection":
        return "compare_contrast"
    if pillar_type == "narrative":
        return "hero_journey"
    return "problem_solution"


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
