from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DocParseResult:
    filename: str | None
    text: str
    paragraphs: list[str]
    parser_provenance: dict[str, Any]


class DeterministicDocParser:
    """
    Deterministic parser for .docx / .odt / plain text.
    Stub for v3.3.0: will use python-docx or mammoth for DOCX.
    Currently accepts plain text or pre-extracted markdown.
    """

    def parse(self, raw_bytes: bytes, filename: str | None = None) -> DocParseResult:
        try:
            text = raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            text = ""

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        return DocParseResult(
            filename=filename,
            text=text,
            paragraphs=paragraphs,
            parser_provenance={
                "parser": "tool_server.parsers.deterministic_doc_parser.DeterministicDocParser",
                "version": "1.0.0",
                "method": "plaintext_paragraph_split",
                "input_bytes": len(raw_bytes),
                "paragraph_count": len(paragraphs),
            },
        )
