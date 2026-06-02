import json
from unittest.mock import MagicMock
import pytest

from agents.research_agent import ResearchAgent


class TestResearchAgentThesis:
    def test_generate_thesis_v0(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = """
        {
            "thesis_statement": "AI regulation will unlock enterprise adoption by 2027.",
            "pillars": [
                {"pillar_index": 0, "pillar_type": "data", "statement": "Market size $500B by 2027"},
                {"pillar_index": 1, "pillar_type": "claim", "statement": "EU AI Act creates legal clarity"}
            ]
        }
        """
        mock_workflow = MagicMock()
        mock_workflow.create_thesis_version.return_value = {"id": "thesis-1"}

        agent = ResearchAgent(workflow_client=mock_workflow, llm_client=mock_llm)
        result = agent.generate_thesis_v0("proj-1", "AI regulation", selected_persona={"title": "VC Partner", "time_budget_minutes": 10})

        assert result["thesis_version_id"] == "thesis-1"
        assert result["pillars_count"] == 2
        mock_workflow.create_thesis_version.assert_called_once()

    def test_thesis_schema_enforcement(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = '{"thesis_statement": "X", "pillars": [{"pillar_index": 0, "pillar_type": "bad_type", "statement": "Y"}]}'
        agent = ResearchAgent(llm_client=mock_llm, workflow_client=MagicMock())

        with pytest.raises(Exception):  # jsonschema.ValidationError for bad_type, Exception for maxItems/duplicates
            agent.generate_thesis_v0("proj-1", "test")

    def test_max_10_pillars(self):
        mock_llm = MagicMock()
        pillars = [{"pillar_index": i, "pillar_type": "claim", "statement": f"P{i}"} for i in range(15)]
        mock_llm.complete.return_value = json.dumps({
            "thesis_statement": "Too many.",
            "pillars": pillars
        })
        agent = ResearchAgent(llm_client=mock_llm, workflow_client=MagicMock())

        with pytest.raises(Exception):  # jsonschema.ValidationError or ValueError
            agent.generate_thesis_v0("proj-1", "test")

    def test_no_duplicate_pillars(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = json.dumps({
            "thesis_statement": "Dupes.",
            "pillars": [
                {"pillar_index": 0, "pillar_type": "claim", "statement": "Same"},
                {"pillar_index": 1, "pillar_type": "claim", "statement": "Same"}
            ]
        })
        agent = ResearchAgent(llm_client=mock_llm, workflow_client=MagicMock())

        with pytest.raises(ValueError, match="Duplicate pillar"):
            agent.generate_thesis_v0("proj-1", "test")
