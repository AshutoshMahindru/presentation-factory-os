from __future__ import annotations

from typing import Any

import pytest

from agents.research_agent import DeepReadMixin, ResearchAgent
from evidence_graph.evidence_linker import DeepReadResult


class _FakeWorkflow:
    """Stub for the WorkflowClient used by DeepReadMixin.

    The agent now delegates cross-store work to the workflow API; this
    fake records the POST and returns a canned response shape.
    """

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._response = response or {
            "project_id": "proj-1",
            "thesis_version_id": "thesis-1",
            "pillar_links": [
                {
                    "pillar_id": "pillar-1",
                    "pillar_index": 0,
                    "pillar_type": "data",
                    "statement": "Margins expanding.",
                    "source_ids": ["source-A", "source-B"],
                },
                {
                    "pillar_id": "pillar-2",
                    "pillar_index": 1,
                    "pillar_type": "narrative",
                    "statement": "Founder moat.",
                    "source_ids": [],
                },
            ],
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:  # noqa: D401
        self.calls.append((path, payload))
        return self._response


def test_deep_read_mixin_is_composed_into_research_agent_mro() -> None:
    assert DeepReadMixin in ResearchAgent.__mro__
    assert hasattr(ResearchAgent, "deep_read_sources_for_pillars")


def test_research_agent_deep_read_calls_workflow_endpoint_and_returns_result() -> None:
    wf = _FakeWorkflow()
    agent = ResearchAgent(workflow_client=wf)  # type: ignore[arg-type]

    result = agent.deep_read_sources_for_pillars(
        project_id="proj-1", thesis_version_id="thesis-1"
    )

    # Endpoint called with the right shape
    assert len(wf.calls) == 1
    path, payload = wf.calls[0]
    assert path == "/projects/proj-1/research/deep-read-sources"
    assert payload == {"thesis_version_id": "thesis-1"}

    # Result hydrates the dataclass from the API shape
    assert isinstance(result, DeepReadResult)
    assert result.project_id == "proj-1"
    assert result.thesis_version_id == "thesis-1"
    assert len(result.pillar_links) == 2
    assert result.pillar_links[0].pillar_id == "pillar-1"
    assert result.pillar_links[0].source_ids == ("source-A", "source-B")
    assert result.pillar_links[1].pillar_id == "pillar-2"
    assert result.pillar_links[1].source_ids == ()
    assert result.pillar_ids_with_no_sources() == ("pillar-2",)
    assert result.total_sources() == 2


def test_research_agent_deep_read_handles_empty_pillar_links() -> None:
    wf = _FakeWorkflow(
        response={
            "project_id": "proj-1",
            "thesis_version_id": "thesis-1",
            "pillar_links": [],
        }
    )
    agent = ResearchAgent(workflow_client=wf)  # type: ignore[arg-type]
    result = agent.deep_read_sources_for_pillars(
        project_id="proj-1", thesis_version_id="thesis-1"
    )
    assert result.pillar_links == ()
    assert result.total_sources() == 0
    assert result.pillar_ids_with_no_sources() == ()
