import pytest
from fastapi.testclient import TestClient

from tool_server.app import app


client = TestClient(app)


class TestSourceIngestionE2E:
    def test_parse_web_endpoint(self):
        payload = {
            "uri": "http://example.com/annual-report",
            "html": "<html><title>Annual Report</title><body><h1>Results</h1><p>Revenue up 40%.</p></body></html>"
        }
        resp = client.post("/tools/parse_web", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Annual Report"
        assert "Revenue up 40%." in data["text"]
        assert "quality_score" in data
        assert data["quality_score"]["authority"] > 0
        assert "parser_provenance" in data

    def test_parse_pdf_endpoint(self):
        # Upload plaintext as fake PDF
        resp = client.post(
            "/tools/parse_pdf",
            files={"file": ("report.txt", b"Executive Summary\n\nRevenue grew 40%.")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Executive Summary" in data["text"]
        assert "quality_score" in data
        assert "parser_provenance" in data

    def test_parse_document_endpoint(self):
        resp = client.post(
            "/tools/parse_document",
            files={"file": ("memo.txt", b"Memo\n\nPoint one.\n\nPoint two.")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["paragraphs"]) == 3

    def test_no_llm_inside_tool_server(self):
        # Policy check: no LLM client imported in parsers
        import tool_server.parsers.web_parser as wp
        import tool_server.parsers.pdf_parser as pp
        assert not hasattr(wp, "OpenAI")
        assert not hasattr(pp, "Anthropic")
