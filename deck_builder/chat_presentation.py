from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import re
from typing import Any, Mapping

from api.exports import export_deck
from deck_builder.export_gate import ExportGate
from deck_builder.render_web_deck import render_web_deck
from deck_builder.slide_factory import SlideFactory
from deck_builder.slide_schema_validator import SlideSchemaValidator


SUPPORTED_AUDIENCES = {
    "board": ("board", "directors"),
    "investor": ("investor", "series a", "fundraise", "venture"),
    "ic_partner": ("ic", "investment committee", "partner"),
    "cfo": ("cfo", "finance", "unit economics", "margin"),
    "operator": ("operator", "ops", "execution"),
}


@dataclass(frozen=True)
class PresentationBrief:
    topic: str
    audience: str
    objective: str
    tone: str
    slide_count: int
    source: str
    confidence: float
    gaps: tuple[str, ...]
    recommended_next_action: str

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PresentationRun:
    run_id: str
    brief: PresentationBrief
    pillars: tuple[dict[str, Any], ...]
    slides: tuple[dict[str, Any], ...]
    deck: dict[str, Any]
    export_gate: dict[str, Any]
    web_preview: dict[str, Any]
    export_metadata: dict[str, Any]
    evidence_gaps: tuple[str, ...]
    recommended_next_action: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "brief": self.brief.to_payload(),
            "pillars": list(self.pillars),
            "slides": list(self.slides),
            "deck": self.deck,
            "export_gate": self.export_gate,
            "web_preview": self.web_preview,
            "export_metadata": self.export_metadata,
            "evidence_gaps": list(self.evidence_gaps),
            "recommended_next_action": self.recommended_next_action,
        }


class ChatPresentationPlanner:
    """Deterministic local chat-to-presentation planner.

    This is the fallback-first orchestration layer: it turns a user chat message
    into a validated preview deck without remote model calls or API keys.
    """

    def create_presentation_from_chat(
        self,
        message: str,
        project_context: Mapping[str, Any] | None = None,
    ) -> PresentationRun:
        clean_message = _normalize_message(message)
        context = dict(project_context or {})
        brief = self._build_brief(clean_message, context)
        run_id = _run_id(clean_message, context)

        source_refs = _source_refs(context, run_id)
        evidence_gaps = _evidence_gaps(context, brief)
        pillars = tuple(self._build_pillars(brief))
        source_refs_by_pillar = {pillar["id"]: source_refs for pillar in pillars}

        slides = tuple(
            SlideFactory().build_slide_jobs_from_pillars(
                pillars,
                source_refs_by_pillar=source_refs_by_pillar,
                financial_cells_by_pillar=_financial_cells_by_pillar(context, pillars),
                scenario=str(context.get("scenario") or "base"),
            )
        )

        validator = SlideSchemaValidator.from_file()
        for slide in slides:
            validator.assert_valid(slide)

        deck = _deck_payload(slides, context)
        gate_result = ExportGate().evaluate(deck)
        rendered = render_web_deck(deck)

        recommended_next_action = _recommended_next_action(
            evidence_gaps=evidence_gaps,
            export_allowed=gate_result.export_allowed,
        )

        return PresentationRun(
            run_id=run_id,
            brief=brief,
            pillars=pillars,
            slides=slides,
            deck=deck,
            export_gate={
                "export_allowed": gate_result.export_allowed,
                "blocking_reasons": list(gate_result.blocking_reasons),
                "warnings": list(gate_result.warnings),
            },
            web_preview={
                "artifact_type": "web_deck_preview",
                "mime_type": "text/html",
                "html": rendered.html,
                "content_hash": rendered.content_hash,
                "slide_count": rendered.slide_count,
                "warnings": list(rendered.warnings),
            },
            export_metadata=export_deck(deck),
            evidence_gaps=evidence_gaps,
            recommended_next_action=recommended_next_action,
        )

    def _build_brief(self, message: str, context: Mapping[str, Any]) -> PresentationBrief:
        explicit_audience = str(context.get("audience") or "").strip()
        audience = explicit_audience or _infer_audience(message)
        topic = str(context.get("topic") or "").strip() or _infer_topic(message)
        objective = (
            str(context.get("objective") or "").strip()
            or str(context.get("decision_required") or "").strip()
            or _infer_objective(message, audience)
        )
        slide_count = _infer_slide_count(message, context)

        gaps: list[str] = []
        confidence = 0.74
        if audience == "operator" and not explicit_audience:
            gaps.append("Confirm the target audience for the presentation.")
            confidence -= 0.12
        if not _has_external_sources(context):
            gaps.append("Attach external source refs before treating claims as evidence-backed.")
            confidence -= 0.18
        if not str(context.get("decision_required") or "").strip():
            gaps.append("Confirm the specific decision the presentation should ask for.")
            confidence -= 0.08

        return PresentationBrief(
            topic=topic,
            audience=audience,
            objective=objective,
            tone=str(context.get("tone") or "operator-grade, direct, evidence-aware"),
            slide_count=slide_count,
            source="deterministic_chat_planner",
            confidence=max(0.1, round(confidence, 2)),
            gaps=tuple(gaps),
            recommended_next_action=_brief_next_action(gaps),
        )

    def _build_pillars(self, brief: PresentationBrief) -> list[dict[str, Any]]:
        base = [
            (
                "narrative",
                f"Frame {brief.topic} around the {brief.audience} audience's decision context.",
                "low",
            ),
            (
                "data",
                f"Show the evidence base that makes {brief.topic} worth acting on.",
                "high",
            ),
            (
                "financial",
                f"Connect {brief.topic} to validated economics and operating constraints.",
                "high",
            ),
            (
                "objection",
                f"Address the main risks that could block {brief.objective}.",
                "medium",
            ),
            (
                "claim",
                f"Ask the {brief.audience} audience to approve the next step for {brief.topic}.",
                "medium",
            ),
        ]
        selected = base[: max(3, min(brief.slide_count, len(base)))]
        return [
            {
                "id": f"pillar_{index:03d}",
                "pillar_index": index - 1,
                "pillar_type": pillar_type,
                "statement": statement,
                "materiality": materiality,
            }
            for index, (pillar_type, statement, materiality) in enumerate(selected, start=1)
        ]


def create_presentation_from_chat(
    message: str,
    project_context: Mapping[str, Any] | None = None,
) -> PresentationRun:
    return ChatPresentationPlanner().create_presentation_from_chat(message, project_context)


def _normalize_message(message: str) -> str:
    clean = " ".join(str(message or "").split())
    if not clean:
        raise ValueError("chat message is required")
    return clean


def _run_id(message: str, context: Mapping[str, Any]) -> str:
    project_id = str(context.get("project_id") or "standalone")
    digest = sha256(f"{project_id}\n{message}".encode("utf-8")).hexdigest()[:12]
    return f"presentation_run_{digest}"


def _infer_audience(message: str) -> str:
    lower = message.lower()
    for audience, needles in SUPPORTED_AUDIENCES.items():
        if any(_contains_phrase(lower, needle) for needle in needles):
            return audience
    return "operator"


def _contains_phrase(text: str, phrase: str) -> bool:
    escaped = re.escape(phrase.lower())
    if " " in phrase:
        return re.search(rf"(?<!\w){escaped}(?!\w)", text) is not None
    return re.search(rf"\b{escaped}\b", text) is not None


def _infer_topic(message: str) -> str:
    text = re.sub(
        r"\b(create|make|build|draft|generate|presentation|deck|slides?|about|for|to)\b",
        " ",
        message,
        flags=re.IGNORECASE,
    )
    topic = " ".join(text.split()).strip(" .,:;-")
    if not topic:
        return "the requested presentation"
    return topic[:140]


def _infer_objective(message: str, audience: str) -> str:
    lower = message.lower()
    if any(token in lower for token in ("approve", "approval", "decision", "greenlight")):
        return "secure a decision"
    if any(token in lower for token in ("raise", "series", "investor", "fundraise")):
        return "support an investor conversation"
    if audience == "board":
        return "drive board alignment"
    return "create an operator-ready presentation"


def _infer_slide_count(message: str, context: Mapping[str, Any]) -> int:
    explicit = context.get("slide_count")
    if explicit is not None:
        try:
            return max(3, min(12, int(explicit)))
        except (TypeError, ValueError):
            pass
    match = re.search(r"\b(\d{1,2})\s*(?:slide|slides)\b", message, flags=re.IGNORECASE)
    if match:
        return max(3, min(12, int(match.group(1))))
    return 5


def _has_external_sources(context: Mapping[str, Any]) -> bool:
    return bool(context.get("source_refs") or context.get("source_ids") or context.get("sources"))


def _source_refs(context: Mapping[str, Any], run_id: str) -> list[str]:
    refs: list[str] = []
    refs.extend(str(ref) for ref in context.get("source_refs", []) or [] if ref)
    refs.extend(str(ref) for ref in context.get("source_ids", []) or [] if ref)
    for source in context.get("sources", []) or []:
        if isinstance(source, Mapping):
            ref = source.get("source_id") or source.get("id")
            if ref:
                refs.append(str(ref))
        elif source:
            refs.append(str(source))
    if not refs:
        refs.append(f"operator_brief_{run_id}")
    return _stable_unique(refs)


def _evidence_gaps(context: Mapping[str, Any], brief: PresentationBrief) -> tuple[str, ...]:
    gaps = list(brief.gaps)
    if not _has_external_sources(context):
        gaps.append("Current preview uses the operator chat prompt as provisional evidence.")
    return tuple(_stable_unique(gaps))


def _financial_cells_by_pillar(
    context: Mapping[str, Any],
    pillars: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    cells = context.get("financial_cells", {}) or {}
    if not cells:
        return {}
    return {
        pillar["id"]: cells
        for pillar in pillars
        if pillar.get("pillar_type") == "financial"
    }


def _deck_payload(slides: tuple[dict[str, Any], ...], context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "slides": list(slides),
        "financial_validation_status": context.get("financial_validation_status"),
        "unsupported_financial_claim_count": int(context.get("unsupported_financial_claim_count", 0) or 0),
        "financial_cells": context.get("financial_cells", {}) or {},
        "sensitive_data_detected": bool(context.get("sensitive_data_detected", False)),
        "pii_exposure_detected": bool(context.get("pii_exposure_detected", False)),
        "artifacts": list(context.get("artifacts", []) or []),
        "pending_source_retraction_count": int(context.get("pending_source_retraction_count", 0) or 0),
        "unprocessed_outbox_count": int(context.get("unprocessed_outbox_count", 0) or 0),
    }


def _recommended_next_action(evidence_gaps: tuple[str, ...], export_allowed: bool) -> str:
    if not export_allowed:
        return "Resolve export gate blockers before sharing the deck."
    if evidence_gaps:
        return "Review the preview, attach external sources, then regenerate for evidence-backed export."
    return "Review the preview and export the deck."


def _brief_next_action(gaps: list[str]) -> str:
    if gaps:
        return "Continue chat with the missing audience, decision, or source details."
    return "Generate the presentation preview."


def _stable_unique(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out
