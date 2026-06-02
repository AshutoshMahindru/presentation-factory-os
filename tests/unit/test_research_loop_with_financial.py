from __future__ import annotations

from typing import Any

import pytest

from agents.base_agent import WorkflowClient
from agents.financial_agent import FinancialReview, FinancialReviewFinding
from agents.research_agent import ResearchAgent


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeWorkflow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, payload))
        if path == "/research-loops/start":
            return {"id": f"loop-{len(self.calls)}"}
        if path.endswith("/finalize"):
            return {"id": path.split("/")[-2]}
        if path.endswith("/thesis-versions"):
            return {"id": f"thesis-{len(self.calls)}"}
        # Other endpoints (stress, etc.) are no-ops for this test
        return {"ok": True}

    def create_thesis_version(
        self, project_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append((f"/projects/{project_id}/thesis-versions", payload))
        return {"id": f"thesis-{len(self.calls)}"}

    def create_source(
        self, project_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append((f"/projects/{project_id}/sources", payload))
        return {"id": f"source-{len(self.calls)}"}


class _FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str, temperature: float = 0.0, max_tokens: int = 2000) -> str:
        self.calls += 1
        import json
        # Source discovery: call N. Thesis: call N+1. If the loop runs
        # multiple iterations, calls alternate (source, thesis, source,
        # thesis, ...). The stub iteration (loop_number > 1) does not
        # call the LLM.
        if self.calls % 2 == 1:
            return json.dumps({"sources": []})
        return json.dumps(
            {
                "thesis_statement": "Test thesis.",
                "pillars": [
                    {
                        "pillar_index": 0,
                        "pillar_type": "financial",
                        "statement": "Margins expanding.",
                    }
                ],
            }
        )


class _FakeFinancialAgent:
    """Stand-in for the real FinancialAgent with a deterministic review."""

    def __init__(self, contradicting_pillar_ids: tuple[str, ...] = ()) -> None:
        self.contradicting = contradicting_pillar_ids
        self.calls: list[tuple[str, str]] = []

    def review_sources_for_thesis(
        self, project_id: str, thesis_version_id: str
    ) -> FinancialReview:
        from agents.financial_agent import QuantitativeContradiction

        self.calls.append((project_id, thesis_version_id))
        contradictions = tuple(
            QuantitativeContradiction(
                pillar_id=pid,
                is_contradiction=True,
                claim_keywords=("growth",),
                cell_ref="FM!Margin",
                cell_value=-1.0,
                direction="positive_claim",
                explanation="stub",
            )
            for pid in self.contradicting
        )
        return FinancialReview(
            project_id=project_id,
            thesis_version_id=thesis_version_id,
            findings=tuple(
                FinancialReviewFinding(
                    pillar_id=pid,
                    verdict="contradicts",
                    rationale="stub",
                )
                for pid in self.contradicting
            ),
            contradictions=contradictions,
        )


# ---------------------------------------------------------------------------
# Convergence tests with and without financial review
# ---------------------------------------------------------------------------


def test_loop_runs_to_completion_without_financial_agent() -> None:
    """The pre-existing behavior is preserved when no financial agent is given."""
    wf = _FakeWorkflow()
    llm = _FakeLLM()
    agent = ResearchAgent(workflow_client=wf, llm_client=llm)  # type: ignore[arg-type]

    result = agent.run_research_loop(
        project_id="proj-1", topic="test", max_loops=1
    )

    assert result["status"] == "max_loops_reached"
    assert result["loops"] == 1
    assert result["stressed_pillar_count"] == 0


def test_loop_integrates_financial_review_when_provided() -> None:
    wf = _FakeWorkflow()
    llm = _FakeLLM()
    agent = ResearchAgent(workflow_client=wf, llm_client=llm)  # type: ignore[arg-type]
    fin = _FakeFinancialAgent(contradicting_pillar_ids=())

    result = agent.run_research_loop(
        project_id="proj-1",
        topic="test",
        max_loops=1,
        financial_agent=fin,
    )

    # Financial review was invoked exactly once.
    assert len(fin.calls) == 1
    assert fin.calls[0][0] == "proj-1"
    # No stressed pillars in this scenario, so stressed count is 0.
    assert result["stressed_pillar_count"] == 0


def test_loop_includes_stressed_pillar_count_in_result() -> None:
    """When financial review finds contradictions, the count surfaces in
    the loop result and the loop body attempts to mark pillars stressed."""
    wf = _FakeWorkflow()
    llm = _FakeLLM()
    agent = ResearchAgent(workflow_client=wf, llm_client=llm)  # type: ignore[arg-type]
    fin = _FakeFinancialAgent(contradicting_pillar_ids=("pillar-1", "pillar-2"))

    result = agent.run_research_loop(
        project_id="proj-1",
        topic="test",
        max_loops=1,
        financial_agent=fin,
    )

    assert result["stressed_pillar_count"] == 2
    # The mark_pillar_stressed endpoint was called twice.
    stress_calls = [c for c in wf.calls if "/stress" in c[0]]
    assert len(stress_calls) == 2


def test_evaluate_convergence_bumps_delta_for_stressed_pillars() -> None:
    """Step 111: the convergence delta grows with stressed pillar count,
    keeping the loop running so the operator can address the contradiction."""
    agent = ResearchAgent(workflow_client=_FakeWorkflow(), llm_client=_FakeLLM())  # type: ignore[arg-type]
    # No stress: delta is 0.03 (below EPSILON).
    assert (
        agent.evaluate_convergence("prev-id", "current-id", stressed_pillar_count=0)
        == 0.03
    )
    # One stress: delta is 0.03 + 0.10 = 0.13 (above EPSILON).
    assert (
        agent.evaluate_convergence("prev-id", "current-id", stressed_pillar_count=1)
        == pytest.approx(0.13)
    )
    # Two stresses: 0.03 + 0.20 = 0.23.
    assert (
        agent.evaluate_convergence("prev-id", "current-id", stressed_pillar_count=2)
        == pytest.approx(0.23)
    )
    # First loop always returns 1.0 regardless of stress.
    assert (
        agent.evaluate_convergence(None, None, stressed_pillar_count=5) == 1.0
    )


def test_loop_keeps_running_when_stress_bumps_delta_above_epsilon() -> None:
    """End-to-end: stress + max_loops=2 should keep the loop running
    because stressed pillars push the delta above EPSILON."""
    wf = _FakeWorkflow()
    llm = _FakeLLM()
    agent = ResearchAgent(workflow_client=wf, llm_client=llm)  # type: ignore[arg-type]
    fin = _FakeFinancialAgent(contradicting_pillar_ids=("p1",))

    result = agent.run_research_loop(
        project_id="proj-1",
        topic="test",
        max_loops=2,
        financial_agent=fin,
    )
    # With stress bumping the delta to 0.13, the loop should run 2 iterations.
    assert result["loops"] == 2
    assert result["status"] == "max_loops_reached"
    assert result["stressed_pillar_count"] == 1
