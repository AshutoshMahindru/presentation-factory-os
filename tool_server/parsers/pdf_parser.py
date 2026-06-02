from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PDFParseResult:
    filename: str | None
    title: str | None
    text: str
    page_count: int | None
    parser_provenance: dict[str, Any]


class PDFParser:
    """
    Deterministic PDF text extractor.
    Stub for production: in v3.3.0, this delegates to pdfminer.six or PyMuPDF.
    For now, operates on raw text fallback or pre-extracted text blobs.
    """

    def parse(self, raw_bytes: bytes, filename: str | None = None) -> PDFParseResult:
        # Production path: detect if bytes are PDF or plain text
        if raw_bytes.startswith(b"%PDF"):
            text, pages = self._extract_from_pdf_bytes(raw_bytes)
        else:
            text = raw_bytes.decode("utf-8", errors="replace")
            pages = None

        title = self._infer_title(text)

        return PDFParseResult(
            filename=filename,
            title=title,
            text=text,
            page_count=pages,
            parser_provenance={
                "parser": "tool_server.parsers.pdf_parser.PDFParser",
                "version": "1.0.0",
                "method": "pdf_bytes_or_plaintext",
                "input_bytes": len(raw_bytes),
                "output_chars": len(text),
            },
        )

    def _extract_from_pdf_bytes(self, raw_bytes: bytes) -> tuple[str, int | None]:
        # Stub: real implementation uses pdfminer.six in v3.3.0
        # For now, extract text between BT/ET markers as minimal deterministic fallback
        text_parts = re.findall(rb"BT\s*(.*?)\s*ET", raw_bytes, re.DOTALL)
        decoded = " ".join(b.decode("utf-8", errors="replace") for b in text_parts)
        # Remove literal PDF commands
        cleaned = re.sub(r"\s+", " ", decoded)
        # Page count from /Type /Page
        pages = len(re.findall(rb"/Type\s*/Page\b", raw_bytes))
        return cleaned, pages if pages > 0 else None

    @staticmethod
    def _infer_title(text: str) -> str | None:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return None
        # Heuristic: first line under 120 chars that looks like a title
        for line in lines[:10]:
            if len(line) < 120 and not line.endswith("."):
                return line
        return lines[0][:120]
