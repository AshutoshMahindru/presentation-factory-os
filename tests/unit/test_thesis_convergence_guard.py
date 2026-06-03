from __future__ import annotations

import json
from typing import Any

import pytest

from agents.financial_agent import FinancialReview, QuantitativeContradiction
from agents.research_agent import ResearchAgent


class _FakeWorkflow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, payload))
        if path == "/research-loops/start":
            return {"id": f"loop-{len(self.calls)}"}
        if path.endswith("/finalize"):
            return {"id": path.split("/")[-2]}
        return {"ok": True}

    def create_thesis_version(
        self, project_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append((f"/projects/{project_id}/thesis-versions", payload))
        return {"id": "thesis-1"}

    def create_source(
        self, project_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append((f"/projects/{project_id}/sources", payload))
        return {"id": "source-1"}


class _FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def complete(
        self, prompt: str, temperature: float = 0.0, max_tokens: int = 2000
    ) -> str:
        self.calls += 1
        if self.calls % 2 == 1:
            return json.dumps({"sources": []})
        return json.dumps(
            {
                "thesis_statement": "Financial thesis.",
                "pillars": [
                    {
                        "pillar_index": 0,
                        "pillar_type": "financial",
                        "statement": "Margins expanding.",
                    }
                ],
            }
        )


class _ContradictingFinancialAgent:
    def __init__(self, pillar_ids: tuple[str, ...]) -> None:
        self.pillar_ids = pillar_ids
        self.calls: list[tuple[str, str]] = []

    def review_sources_for_thesis(
        self, project_id: str, thesis_version_id: str
    ) -> FinancialReview:
        self.calls.append((project_id, thesis_version_id))
        return FinancialReview(
            project_id=project_id,
            thesis_version_id=thesis_version_id,
            contradictions=tuple(
                QuantitativeContradiction(
                    pillar_id=pillar_id,
                    is_contradiction=True,
                    claim_keywords=("expanding",),
                    cell_ref="FM!Margin",
                    cell_value=-0.05,
                    direction="positive_claim",
                    explanation="stub",
                )
                for pillar_id in self.pillar_ids
            ),
        )


def test_convergence_guard_crosses_epsilon_only_when_pillars_are_stressed() -> None:
    agent = ResearchAgent(workflow_client=_FakeWorkflow(), llm_client=_FakeLLM())  # type: ignore[arg-type]

    stable_delta = agent.evaluate_convergence(
        "previous-thesis",
        object(),
        stressed_pillar_count=0,
    )
    stressed_delta = agent.evaluate_convergence(
        "previous-thesis",
        object(),
        stressed_pillar_count=1,
    )

    assert stable_delta < agent.EPSILON
    assert stressed_delta > agent.EPSILON
    assert stressed_delta == pytest.approx(0.13)


def test_convergence_guard_keeps_loop_running_and_marks_stressed_pillar() -> None:
    workflow = _FakeWorkflow()
    agent = ResearchAgent(workflow_client=workflow, llm_client=_FakeLLM())  # type: ignore[arg-type]
    financial_agent = _ContradictingFinancialAgent(("pillar-1",))

    result = agent.run_research_loop(
        project_id="project-1",
        topic="unit test",
        max_loops=2,
        financial_agent=financial_agent,
    )

    assert result["status"] == "max_loops_reached"
    assert result["loops"] == 2
    assert result["convergence_delta"] > agent.EPSILON
    assert result["stressed_pillar_count"] == 1
    assert financial_agent.calls == [
        ("project-1", "thesis-1"),
        ("project-1", "thesis-1"),
    ]

    stress_calls = [call for call in workflow.calls if call[0].endswith("/stress")]
    assert stress_calls == [
        (
            "/thesis-versions/thesis-1/pillars/pillar-1/stress",
            {"stress_status": "stressed"},
        ),
        (
            "/thesis-versions/thesis-1/pillars/pillar-1/stress",
            {"stress_status": "stressed"},
        ),
    ]
