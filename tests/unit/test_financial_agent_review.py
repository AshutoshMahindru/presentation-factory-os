from __future__ import annotations

import json
from typing import Any

import pytest

from agents.financial_agent import (
    NEGATIVE_KEYWORDS,
    POSITIVE_KEYWORDS,
    FinancialAgent,
    FinancialReview,
    FinancialReviewFinding,
    QuantitativeContradiction,
    REVIEW_FINDING_SCHEMA,
)


# ---------------------------------------------------------------------------
# Fake clients
# ---------------------------------------------------------------------------


class _FakeWorkflow:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._response = response or {
            "project_id": "proj-1",
            "thesis_version_id": "thesis-1",
            "pillars": [],
            "cells_by_pillar": {},
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, payload))
        return self._response


class _FakeLLM:
    def __init__(self, response: str = "") -> None:
        self.calls: list[str] = []
        self._response = response or json.dumps(
            {"findings": [{"pillar_id": "p1", "verdict": "supports", "rationale": "ok"}]}
        )

    def complete(self, prompt: str, temperature: float = 0.0, max_tokens: int = 2000) -> str:
        self.calls.append(prompt)
        return self._response


# ---------------------------------------------------------------------------
# _check_quantitative_contradiction
# ---------------------------------------------------------------------------


def test_contradiction_positive_claim_negative_value() -> None:
    agent = FinancialAgent(workflow_client=_FakeWorkflow(), llm_client=_FakeLLM())  # type: ignore[arg-type]
    c = agent._check_quantitative_contradiction(
        pillar_id="p1",
        claim_statement="Margins are expanding rapidly.",
        cell_ref="FM!Margin",
        cell_value=-0.05,
    )
    assert c.is_contradiction is True
    assert "expanding" in c.claim_keywords
    assert c.direction == "positive_claim"
    assert "negative" in c.explanation


def test_contradiction_negative_claim_positive_value() -> None:
    agent = FinancialAgent(workflow_client=_FakeWorkflow(), llm_client=_FakeLLM())  # type: ignore[arg-type]
    c = agent._check_quantitative_contradiction(
        pillar_id="p1",
        claim_statement="Revenue is declining year over year.",
        cell_ref="FM!RevYoY",
        cell_value=0.12,
    )
    assert c.is_contradiction is True
    assert "declining" in c.claim_keywords
    assert c.direction == "negative_claim"


def test_no_contradiction_when_sign_matches() -> None:
    agent = FinancialAgent(workflow_client=_FakeWorkflow(), llm_client=_FakeLLM())  # type: ignore[arg-type]
    c = agent._check_quantitative_contradiction(
        pillar_id="p1",
        claim_statement="Margins are expanding rapidly.",
        cell_ref="FM!Margin",
        cell_value=0.05,
    )
    assert c.is_contradiction is False
    assert c.direction == "positive_claim"


def test_no_contradiction_for_zero_value() -> None:
    agent = FinancialAgent(workflow_client=_FakeWorkflow(), llm_client=_FakeLLM())  # type: ignore[arg-type]
    c = agent._check_quantitative_contradiction(
        pillar_id="p1",
        claim_statement="Margins expanding.",
        cell_ref="FM!Margin",
        cell_value=0.0,
    )
    assert c.is_contradiction is False


def test_no_contradiction_for_mixed_directional_language() -> None:
    agent = FinancialAgent(workflow_client=_FakeWorkflow(), llm_client=_FakeLLM())  # type: ignore[arg-type]
    c = agent._check_quantitative_contradiction(
        pillar_id="p1",
        claim_statement="Margins are growing but cash is declining.",
        cell_ref="FM!Margin",
        cell_value=-0.05,
    )
    assert c.is_contradiction is False
    assert c.direction == "unknown"


def test_no_contradiction_when_no_directional_language() -> None:
    agent = FinancialAgent(workflow_client=_FakeWorkflow(), llm_client=_FakeLLM())  # type: ignore[arg-type]
    c = agent._check_quantitative_contradiction(
        pillar_id="p1",
        claim_statement="The company sells software.",
        cell_ref="FM!Rev",
        cell_value=-100.0,
    )
    assert c.is_contradiction is False
    assert c.direction == "unknown"


def test_tokenize_skips_short_and_punctuation() -> None:
    agent = FinancialAgent(workflow_client=_FakeWorkflow(), llm_client=_FakeLLM())  # type: ignore[arg-type]
    toks = agent._tokenize("The growth, is strong! Up by 2%")
    assert "growth" in toks
    assert "strong" in toks
    # 1-2 char tokens dropped
    assert "is" not in toks


def test_keyword_sets_are_non_empty_and_disjoint() -> None:
    assert POSITIVE_KEYWORDS
    assert NEGATIVE_KEYWORDS
    assert POSITIVE_KEYWORDS.isdisjoint(NEGATIVE_KEYWORDS)


# ---------------------------------------------------------------------------
# review_sources_for_thesis
# ---------------------------------------------------------------------------


def test_review_returns_findings_and_contradictions() -> None:
    wf = _FakeWorkflow(
        response={
            "project_id": "proj-1",
            "thesis_version_id": "thesis-1",
            "pillars": [
                {
                    "id": "p1",
                    "pillar_index": 0,
                    "pillar_type": "financial",
                    "statement": "Margins expanding.",
                    "stress_status": "stable",
                },
                {
                    "id": "p2",
                    "pillar_index": 1,
                    "pillar_type": "data",
                    "statement": "Revenue growing.",
                    "stress_status": "stable",
                },
            ],
            "cells_by_pillar": {
                "p1": [
                    {
                        "id": "c1",
                        "cell_ref": "FM!Margin",
                        "label": "Margin",
                        "value": -0.05,
                        "unit": "USD",
                        "scenario": "base",
                        "formula": "x",
                        "artifact_status": "active",
                    }
                ],
                "p2": [
                    {
                        "id": "c2",
                        "cell_ref": "FM!Rev",
                        "label": "Revenue YoY",
                        "value": 0.10,
                        "unit": "USD",
                        "scenario": "base",
                        "formula": "y",
                        "artifact_status": "active",
                    }
                ],
            },
        }
    )
    llm = _FakeLLM(
        response=json.dumps(
            {
                "findings": [
                    {"pillar_id": "p1", "verdict": "contradicts", "rationale": "margin -5%", "cell_refs": ["FM!Margin"]},
                    {"pillar_id": "p2", "verdict": "supports", "rationale": "rev +10%", "cell_refs": ["FM!Rev"]},
                ]
            }
        )
    )
    agent = FinancialAgent(workflow_client=wf, llm_client=llm)  # type: ignore[arg-type]
    review = agent.review_sources_for_thesis(
        project_id="proj-1", thesis_version_id="thesis-1"
    )
    assert isinstance(review, FinancialReview)
    assert len(review.findings) == 2
    assert len(review.contradictions) == 1
    # Only p1 should be flagged
    assert review.pillars_with_contradictions() == ("p1",)
    # The contradiction is the margin cell vs the "expanding" claim
    c = review.contradictions[0]
    assert c.pillar_id == "p1"
    assert c.cell_ref == "FM!Margin"
    assert c.is_contradiction is True


def test_review_handles_missing_pillars() -> None:
    wf = _FakeWorkflow(
        response={
            "project_id": "proj-1",
            "thesis_version_id": "thesis-1",
            "pillars": [],
            "cells_by_pillar": {},
        }
    )
    llm = _FakeLLM()
    agent = FinancialAgent(workflow_client=wf, llm_client=llm)  # type: ignore[arg-type]
    review = agent.review_sources_for_thesis(
        project_id="proj-1", thesis_version_id="thesis-1"
    )
    assert review.findings == ()
    assert review.contradictions == ()
    # The LLM is not called when there are no pillars.
    assert llm.calls == []


def test_review_handles_invalid_llm_json() -> None:
    wf = _FakeWorkflow(
        response={
            "project_id": "proj-1",
            "thesis_version_id": "thesis-1",
            "pillars": [
                {
                    "id": "p1",
                    "pillar_index": 0,
                    "pillar_type": "financial",
                    "statement": "x",
                    "stress_status": "stable",
                }
            ],
            "cells_by_pillar": {},
        }
    )
    llm = _FakeLLM(response="not-json")
    agent = FinancialAgent(workflow_client=wf, llm_client=llm)  # type: ignore[arg-type]
    review = agent.review_sources_for_thesis(
        project_id="proj-1", thesis_version_id="thesis-1"
    )
    # No findings parsed; a single neutral sentinel captures the failure.
    assert len(review.findings) == 1
    assert review.findings[0].verdict == "neutral"
    assert "review_parse_error" in review.findings[0].rationale
    assert "review_parse_error" in review.summary


def test_review_handles_schema_violation_from_llm() -> None:
    wf = _FakeWorkflow(
        response={
            "project_id": "proj-1",
            "thesis_version_id": "thesis-1",
            "pillars": [
                {
                    "id": "p1",
                    "pillar_index": 0,
                    "pillar_type": "financial",
                    "statement": "x",
                    "stress_status": "stable",
                }
            ],
            "cells_by_pillar": {},
        }
    )
    # verdict is not in the enum
    llm = _FakeLLM(
        response=json.dumps(
            {"findings": [{"pillar_id": "p1", "verdict": "MAYBE", "rationale": "x"}]}
        )
    )
    agent = FinancialAgent(workflow_client=wf, llm_client=llm)  # type: ignore[arg-type]
    review = agent.review_sources_for_thesis(
        project_id="proj-1", thesis_version_id="thesis-1"
    )
    assert len(review.findings) == 1
    assert "review_parse_error" in review.findings[0].rationale


def test_review_calls_workflow_endpoint_with_correct_path() -> None:
    wf = _FakeWorkflow()
    agent = FinancialAgent(workflow_client=wf, llm_client=_FakeLLM())  # type: ignore[arg-type]
    agent.review_sources_for_thesis(
        project_id="proj-99", thesis_version_id="thesis-42"
    )
    assert len(wf.calls) == 1
    path, payload = wf.calls[0]
    assert path == "/projects/proj-99/thesis-versions/thesis-42/financial-review-context"
    assert payload == {}


# ---------------------------------------------------------------------------
# FinancialReview helpers
# ---------------------------------------------------------------------------


def test_pillars_with_contradictions_dedupes() -> None:
    review = FinancialReview(
        project_id="p",
        thesis_version_id="t",
        contradictions=(
            QuantitativeContradiction(
                pillar_id="p1", is_contradiction=True,
                claim_keywords=("growth",), cell_ref="x",
                cell_value=-1.0, direction="positive_claim", explanation="e",
            ),
            QuantitativeContradiction(
                pillar_id="p1", is_contradiction=True,
                claim_keywords=("growth",), cell_ref="y",
                cell_value=-2.0, direction="positive_claim", explanation="e",
            ),
            QuantitativeContradiction(
                pillar_id="p2", is_contradiction=True,
                claim_keywords=("decline",), cell_ref="z",
                cell_value=1.0, direction="negative_claim", explanation="e",
            ),
        ),
    )
    assert review.pillars_with_contradictions() == ("p1", "p2")


def test_pillars_with_contradictions_ignores_non_contradictions() -> None:
    review = FinancialReview(
        project_id="p",
        thesis_version_id="t",
        contradictions=(
            QuantitativeContradiction(
                pillar_id="p1", is_contradiction=False,
                claim_keywords=(), cell_ref="x",
                cell_value=1.0, direction="unknown", explanation="e",
            ),
        ),
    )
    assert review.pillars_with_contradictions() == ()


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_review_finding_schema_lists_expected_verdicts() -> None:
    verdicts = REVIEW_FINDING_SCHEMA["properties"]["findings"]["items"]["properties"]["verdict"]["enum"]
    assert set(verdicts) == {
        "supports",
        "weakly_supports",
        "neutral",
        "contradicts",
        "missing_data",
    }
