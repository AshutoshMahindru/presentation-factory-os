from unittest.mock import MagicMock
from uuid import uuid4
import pytest

from agents.research_agent import ResearchAgent


class TestResearchAgent:
    def test_discovers_and_registers_sources(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = """
        {
            "sources": [
                {"uri": "https://sec.gov/10k.pdf", "title": "10-K", "source_type": "pdf", "summary": "Annual report"},
                {"uri": "https://example.com/blog", "title": "Blog", "source_type": "web", "summary": "Opinion piece"}
            ]
        }
        """

        mock_workflow = MagicMock()
        mock_workflow.create_source.side_effect = [
            {"id": "src-aaa"},
            {"id": "src-bbb"},
        ]

        agent = ResearchAgent(workflow_client=mock_workflow, llm_client=mock_llm)
        ids = agent.discover_and_register_sources("proj-123", "AI regulation")

        assert len(ids) == 2
        assert mock_workflow.create_source.call_count == 2
        args, kwargs = mock_workflow.create_source.call_args_list[0]
        assert args[0] == "proj-123"
        assert args[1]["uri"] == "https://sec.gov/10k.pdf"

    def test_skips_invalid_uris(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = """
        {
            "sources": [
                {"uri": "not-a-url", "title": "Bad", "source_type": "web", "summary": "x"},
                {"uri": "https://valid.com/doc.pdf", "title": "Good", "source_type": "pdf", "summary": "y"}
            ]
        }
        """
        mock_workflow = MagicMock()
        mock_workflow.create_source.return_value = {"id": "src-ccc"}

        agent = ResearchAgent(workflow_client=mock_workflow, llm_client=mock_llm)
        ids = agent.discover_and_register_sources("proj-456", "test")

        assert len(ids) == 1
        mock_workflow.create_source.assert_called_once()

    def test_no_direct_db_imports(self):
        import agents.research_agent as mod
        import inspect
        source = inspect.getsource(mod)
        assert "import psycopg" not in source
        assert "from system.source_register_repository" not in source
        assert "ConnectionPool" not in source

    def test_extracts_json_from_markdown_fence(self):
        raw = "```json\n{\"sources\":[]}\n```"
        result = ResearchAgent._extract_json(raw)
        assert result.strip() == '{"sources":[]}'

    def test_validates_uri(self):
        assert ResearchAgent._is_valid_uri("https://example.com") is True
        assert ResearchAgent._is_valid_uri("ftp://example.com") is False
        assert ResearchAgent._is_valid_uri("not-a-url") is False
