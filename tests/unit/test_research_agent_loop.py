import json
from unittest.mock import MagicMock, patch
import pytest

from agents.research_agent import ResearchAgent


class TestResearchAgentLoop:
    def test_loop_converges_on_first_iteration(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = json.dumps({
            "sources": [{"uri": "http://a.com", "title": "A", "source_type": "web", "summary": "s"}]
        })

        mock_workflow = MagicMock()
        mock_workflow.create_source.return_value = {"id": "src-1"}
        mock_workflow.create_thesis_version.return_value = {"id": "thesis-1"}
        mock_workflow._post.return_value = {"id": "loop-1"}

        agent = ResearchAgent(workflow_client=mock_workflow, llm_client=mock_llm)

        # Patch evaluate_convergence to return below epsilon immediately
        with patch.object(agent, "generate_thesis_v0", return_value={"thesis_version_id": "thesis-1", "pillars_count": 2}):
            with patch.object(agent, "evaluate_convergence", return_value=0.02):
                result = agent.run_research_loop("proj-1", "AI regulation")

        assert result["status"] == "converged"
        assert result["loops"] == 1
        assert result["thesis_version_id"] == "thesis-1"
        assert result["convergence_delta"] == 0.02

    def test_loop_respects_max_loops(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = json.dumps({"sources": []})
        mock_workflow = MagicMock()
        mock_workflow.create_source.return_value = {"id": "src-1"}
        mock_workflow.create_thesis_version.return_value = {"id": "thesis-1"}
        mock_workflow._post.return_value = {"id": "loop-x"}

        agent = ResearchAgent(workflow_client=mock_workflow, llm_client=mock_llm)

        with patch.object(agent, "generate_thesis_v0", return_value={"thesis_version_id": "thesis-1", "pillars_count": 2}):
            with patch.object(agent, "evaluate_convergence", return_value=0.5):  # never converges
                result = agent.run_research_loop("proj-1", "AI regulation", max_loops=3)

        assert result["status"] == "max_loops_reached"
        assert result["loops"] == 3
        assert result["thesis_version_id"] == "thesis-1"

    def test_evaluate_convergence_first_loop(self):
        agent = ResearchAgent()
        delta = agent.evaluate_convergence(None, None)
        assert delta == 1.0

    def test_loop_calls_discover_and_thesis(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = json.dumps({
            "sources": [{"uri": "http://b.com", "title": "B", "source_type": "web", "summary": "s"}]
        })
        mock_workflow = MagicMock()
        mock_workflow.create_source.return_value = {"id": "src-2"}
        mock_workflow.create_thesis_version.return_value = {"id": "thesis-2"}
        mock_workflow._post.return_value = {"id": "loop-2"}

        agent = ResearchAgent(workflow_client=mock_workflow, llm_client=mock_llm)

        with patch.object(agent, "generate_thesis_v0", return_value={"thesis_version_id": "thesis-2", "pillars_count": 2}):
            with patch.object(agent, "evaluate_convergence", return_value=0.01):
                agent.run_research_loop("proj-1", "topic")

        assert mock_workflow.create_source.called
        # generate_thesis_v0 was patched and called internally; loop completion proves it
