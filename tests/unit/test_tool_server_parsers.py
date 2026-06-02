from tool_server.parsers.web_parser import WebParser
from tool_server.parsers.pdf_parser import PDFParser
from tool_server.parsers.deterministic_doc_parser import DeterministicDocParser


class TestWebParser:
    def test_extracts_title_and_text(self):
        html = "<html><head><title>Report 2024</title></head><body><h1>Intro</h1><p>Revenue grew.</p></body></html>"
        result = WebParser().parse(html, "http://example.com/report")
        assert result.title == "Report 2024"
        assert "Revenue grew." in result.text
        assert result.headings == ["Intro"]
        assert "http://example.com/report" in [result.uri]

    def test_parser_provenance_present(self):
        result = WebParser().parse("<html></html>", "http://a.com")
        assert result.parser_provenance["parser"] == "tool_server.parsers.web_parser.WebParser"
        assert "version" in result.parser_provenance

    def test_dedupes_links(self):
        html = '<a href="/a"></a><a href="/a"></a><a href="http://other.com/b"></a>'
        result = WebParser().parse(html, "http://example.com")
        assert result.links == ["http://example.com/a", "http://other.com/b"]


class TestPDFParser:
    def test_plaintext_fallback(self):
        text = "Title\n\nParagraph one.\n\nParagraph two."
        result = PDFParser().parse(text.encode("utf-8"), filename="doc.txt")
        assert result.text == text
        assert result.title == "Title"

    def test_pdf_stub_extracts_pages(self):
        # Minimal PDF header with fake page markers for deterministic stub
        pdf = b"%PDF-1.4\n/Type /Page\n/Type /Page\nBT (Hello) ET"
        result = PDFParser().parse(pdf, filename="test.pdf")
        assert result.page_count == 2
        assert "Hello" in result.text

    def test_provenance_present(self):
        result = PDFParser().parse(b"text", "f.txt")
        assert result.parser_provenance["parser"] == "tool_server.parsers.pdf_parser.PDFParser"


class TestDocParser:
    def test_paragraph_split(self):
        text = "P1.\n\nP2.\n\nP3."
        result = DeterministicDocParser().parse(text.encode("utf-8"))
        assert result.paragraphs == ["P1.", "P2.", "P3."]
        assert result.parser_provenance["paragraph_count"] == 3
