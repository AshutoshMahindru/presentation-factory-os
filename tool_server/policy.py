from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceQualityScore:
    authority: float = 0.0  # 0-1 based on domain TLD and known publisher list
    recency: float = 0.0    # 0-1 based on publication year vs now
    completeness: float = 0.0  # 0-1 based on text length vs expected for type
    provenance_chain: list[str] = None  # e.g. ["pdfminer 0.0.1", "web_parser 1.0.0"]


class SourceQualityPolicy:
    """
    Deterministic heuristic scoring for ingested sources.
    No LLM. Rules are explicit and auditable.
    """

    KNOWN_PUBLISHERS = {
        "sec.gov", "mckinsey.com", "bcg.com", "bain.com",
        "nature.com", "science.org", "arxiv.org", "reuters.com",
        "bloomberg.com", "ft.com", "economist.com",
    }

    def score_web(self, uri: str, title: str | None, text: str) -> dict[str, Any]:
        from urllib.parse import urlparse
        domain = urlparse(uri).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        authority = 0.5
        if any(domain.endswith(pub) or domain == pub for pub in self.KNOWN_PUBLISHERS):
            authority = 0.95
        elif domain.endswith(".gov"):
            authority = 0.9
        elif domain.endswith(".edu"):
            authority = 0.85

        recency = 0.5  # stub: parse date from title or meta in v3.3.0
        completeness = min(1.0, len(text) / 5000)  # normalize to 5k chars

        return {
            "authority": round(authority, 2),
            "recency": round(recency, 2),
            "completeness": round(completeness, 2),
            "provenance_chain": ["web_parser 1.0.0", "source_quality_policy 1.0.0"],
        }

    def score_pdf(self, filename: str | None, text: str, page_count: int | None) -> dict[str, Any]:
        authority = 0.7 if filename else 0.5
        recency = 0.5
        expected_chars = (page_count or 1) * 3000
        completeness = min(1.0, len(text) / expected_chars) if expected_chars > 0 else 0.0

        return {
            "authority": round(authority, 2),
            "recency": round(recency, 2),
            "completeness": round(completeness, 2),
            "provenance_chain": ["pdf_parser 1.0.0", "source_quality_policy 1.0.0"],
        }

    def score_document(self, filename: str | None, paragraphs: list[str]) -> dict[str, Any]:
        return {
            "authority": 0.6,
            "recency": 0.5,
            "completeness": min(1.0, sum(len(p) for p in paragraphs) / 10000),
            "provenance_chain": ["doc_parser 1.0.0", "source_quality_policy 1.0.0"],
        }
