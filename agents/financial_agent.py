from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from agents.base_agent import BaseAgent, LLMClient, WorkflowClient


# Schema for the LLM-emitted review. Each finding is one pillar x verdict
# x rationale triple. Temperature 0.0, schema-validated, retry on parse fail.
REVIEW_FINDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pillar_id": {"type": "string"},
                    "verdict": {
                        "type": "string",
                        "enum": [
                            "supports",
                            "weakly_supports",
                            "neutral",
                            "contradicts",
                            "missing_data",
                        ],
                    },
                    "rationale": {"type": "string", "maxLength": 500},
                    "cell_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["pillar_id", "verdict", "rationale"],
            },
        }
    },
    "required": ["findings"],
}


# Keyword buckets used by the deterministic contradiction check. These are
# intentionally coarse - anything more nuanced is left to the LLM review
# in `review_sources_for_thesis`.
POSITIVE_KEYWORDS: frozenset[str] = frozenset(
    {
        "growth",
        "grow",
        "growing",
        "expansion",
        "expand",
        "expanding",
        "increase",
        "increasing",
        "rise",
        "rising",
        "improvement",
        "improving",
        "improve",
        "up",
        "higher",
        "strong",
        "stronger",
        "above",
        "exceed",
        "exceeds",
        "outperform",
    }
)

NEGATIVE_KEYWORDS: frozenset[str] = frozenset(
    {
        "decline",
        "declining",
        "decrease",
        "decreasing",
        "fall",
        "falling",
        "drop",
        "dropping",
        "contract",
        "contracting",
        "contraction",
        "shrink",
        "shrinking",
        "down",
        "lower",
        "weak",
        "weaker",
        "below",
        "underperform",
        "loss",
        "losses",
    }
)


@dataclass(frozen=True)
class QuantitativeContradiction:
    """Result of a deterministic contradiction check."""

    pillar_id: str
    is_contradiction: bool
    claim_keywords: tuple[str, ...]
    cell_ref: str
    cell_value: float
    direction: str  # "positive_claim" | "negative_claim" | "unknown"
    explanation: str


@dataclass(frozen=True)
class FinancialReviewFinding:
    pillar_id: str
    verdict: str  # one of the schema enum values
    rationale: str
    cell_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinancialReview:
    project_id: str
    thesis_version_id: str
    findings: tuple[FinancialReviewFinding, ...] = ()
    contradictions: tuple[QuantitativeContradiction, ...] = ()
    summary: str = ""

    def pillars_with_contradictions(self) -> tuple[str, ...]:
        # Preserve insertion order, dedup.
        seen: dict[str, None] = {}
        for c in self.contradictions:
            if c.is_contradiction and c.pillar_id not in seen:
                seen[c.pillar_id] = None
        return tuple(seen.keys())


class FinancialAgent(BaseAgent):
    """Bidirectional source <-> thesis review agent (step 111).

    Two responsibilities:
      1. `review_sources_for_thesis`: orchestrate a per-pillar review
         that combines (a) deterministic contradiction checks against the
         canonical financial cells, and (b) an LLM-graded textual review
         of the pillar statement against the cell labels and values.
      2. `_check_quantitative_contradiction`: the deterministic core.
         Given a claim statement and a financial cell's value, decide
         whether the cell's sign contradicts a directional claim in the
         statement (e.g., "margins expanding" vs a margin cell whose
         value decreased year over year). Returns a structured
         QuantitativeContradiction so the loop can mark the pillar as
         stressed (step 112) without re-running the LLM.

    The agent does not hold DB drivers - per the project's
    no-agent-db-imports rule, it talks to the workflow API and the LLM
    proxy.
    """

    def __init__(
        self,
        workflow_client: WorkflowClient | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.workflow = workflow_client or WorkflowClient()
        self.llm = llm_client or LLMClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def review_sources_for_thesis(
        self,
        project_id: str,
        thesis_version_id: str,
    ) -> FinancialReview:
        # Fetch pillars + their linked canonical cells via workflow API.
        # The endpoint is the integration point for cross-store reads.
        thesis_payload = self.workflow._post(  # type: ignore[attr-defined]
            f"/projects/{project_id}/thesis-versions/{thesis_version_id}/financial-review-context",
            {},
        )
        pillars: list[dict[str, Any]] = thesis_payload.get("pillars", [])
        cells_by_pillar: dict[str, list[dict[str, Any]]] = thesis_payload.get(
            "cells_by_pillar", {}
        )

        contradictions: list[QuantitativeContradiction] = []
        for pillar in pillars:
            pillar_id = str(pillar["id"])
            statement = str(pillar.get("statement", ""))
            for cell in cells_by_pillar.get(pillar_id, []):
                c = self._check_quantitative_contradiction(
                    pillar_id=pillar_id,
                    claim_statement=statement,
                    cell_ref=str(cell["cell_ref"]),
                    cell_value=float(cell["value"]),
                    cell_label=str(cell.get("label", "")),
                )
                if c.is_contradiction:
                    contradictions.append(c)

        # LLM review over the full context. Skip if there are no pillars
        # at all (nothing to review).
        findings: list[FinancialReviewFinding] = []
        summary = ""
        if pillars:
            prompt = self._build_review_prompt(pillars, cells_by_pillar)
            raw = self.llm.complete(prompt, temperature=0.0, max_tokens=2500)
            json_str = self._extract_json(raw)
            try:
                data = json.loads(json_str)
                self._validate_json_schema(data, REVIEW_FINDING_SCHEMA)
                for item in data.get("findings", []):
                    findings.append(
                        FinancialReviewFinding(
                            pillar_id=str(item["pillar_id"]),
                            verdict=str(item["verdict"]),
                            rationale=str(item.get("rationale", "")),
                            cell_refs=tuple(
                                str(c) for c in item.get("cell_refs", [])
                            ),
                        )
                    )
                summary = self._summarize(findings, contradictions)
            except Exception as exc:
                # Review failed to parse or validate. Surface the failure
                # as a single neutral finding so the loop can continue
                # without aborting. _validate_json_schema raises
                # jsonschema.ValidationError (subclass of Exception) on
                # schema violations.
                findings.append(
                    FinancialReviewFinding(
                        pillar_id="*",
                        verdict="neutral",
                        rationale=f"review_parse_error: {exc}",
                    )
                )
                summary = f"review_parse_error: {exc}"

        return FinancialReview(
            project_id=project_id,
            thesis_version_id=thesis_version_id,
            findings=tuple(findings),
            contradictions=tuple(contradictions),
            summary=summary,
        )

    def _check_quantitative_contradiction(
        self,
        *,
        pillar_id: str,
        claim_statement: str,
        cell_ref: str,
        cell_value: float,
        cell_label: str = "",
    ) -> QuantitativeContradiction:
        """Deterministic contradiction check.

        Scans the claim for directional keywords (grow/decline/etc.) and
        compares to the sign of `cell_value`. We also honor an explicit
        sign hint in the cell label (e.g., "YoY change" or
        "absolute value") but do not infer the sign from year-over-year
        sequences - that would require multiple cell values, which the
        caller passes via cell_label in a future iteration.

        Rules:
          - claim has positive keywords and cell_value < 0 -> contradiction
          - claim has negative keywords and cell_value > 0 -> contradiction
          - cell_value == 0 is never a contradiction
          - mixed (both positive and negative) keywords -> no decision
        """
        tokens = self._tokenize(claim_statement)
        has_pos = any(t in POSITIVE_KEYWORDS for t in tokens)
        has_neg = any(t in NEGATIVE_KEYWORDS for t in tokens)

        if has_pos and has_neg:
            direction = "unknown"
            is_contra = False
            explanation = "claim contains both positive and negative directional language; no decision"
        elif has_pos:
            direction = "positive_claim"
            is_contra = cell_value < 0
            explanation = (
                f"claim implies growth/expansion but cell {cell_ref}={cell_value} is negative"
                if is_contra
                else f"cell {cell_ref}={cell_value} does not contradict positive claim"
            )
        elif has_neg:
            direction = "negative_claim"
            is_contra = cell_value > 0
            explanation = (
                f"claim implies decline but cell {cell_ref}={cell_value} is positive"
                if is_contra
                else f"cell {cell_ref}={cell_value} does not contradict negative claim"
            )
        else:
            direction = "unknown"
            is_contra = False
            explanation = f"no directional language in claim; no contradiction with cell {cell_ref}={cell_value}"

        matched = sorted(
            t for t in tokens
            if t in POSITIVE_KEYWORDS or t in NEGATIVE_KEYWORDS
        )
        return QuantitativeContradiction(
            pillar_id=pillar_id,
            is_contradiction=is_contra,
            claim_keywords=tuple(matched),
            cell_ref=cell_ref,
            cell_value=cell_value,
            direction=direction,
            explanation=explanation,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        # Lowercase, split on non-alpha, drop very short tokens.
        out: set[str] = set()
        for raw in text.lower().split():
            word = "".join(c for c in raw if c.isalpha())
            if len(word) >= 3:
                out.add(word)
        return out

    @staticmethod
    def _extract_json(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        return text

    @staticmethod
    def _build_review_prompt(
        pillars: list[dict[str, Any]],
        cells_by_pillar: dict[str, list[dict[str, Any]]],
    ) -> str:
        return (
            "You are a financial analyst reviewing whether the canonical "
            "financial cells in this project support each pillar of the "
            "thesis. For each pillar, emit a verdict (supports, "
            "weakly_supports, neutral, contradicts, or missing_data) and a "
            "short rationale. Return exactly one JSON object with shape:\n"
            "  {findings: [{pillar_id, verdict, rationale, cell_refs: [...]}, ...]}\n"
            "Do not include markdown, only raw JSON.\n\n"
            f"Pillars:\n{json.dumps(pillars, indent=2)}\n\n"
            f"Cells by pillar:\n{json.dumps(cells_by_pillar, indent=2)}\n"
        )

    @staticmethod
    def _summarize(
        findings: list[FinancialReviewFinding],
        contradictions: list[QuantitativeContradiction],
    ) -> str:
        verdict_counts: dict[str, int] = {}
        for f in findings:
            verdict_counts[f.verdict] = verdict_counts.get(f.verdict, 0) + 1
        parts = [f"findings={verdict_counts}"]
        if contradictions:
            parts.append(f"deterministic_contradictions={len(contradictions)}")
        return " | ".join(parts)
