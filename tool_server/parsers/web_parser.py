from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WebParseResult:
    uri: str
    title: str | None
    text: str
    links: list[str]
    headings: list[str]
    parser_provenance: dict[str, Any]


class WebParser:
    """
    Deterministic web content parser.
    No LLM inference. Extracts structure via regex and HTML heuristics.
    """

    def parse(self, html: str, base_uri: str) -> WebParseResult:
        title = self._extract_title(html)
        text = self._extract_text(html)
        links = self._extract_links(html, base_uri)
        headings = self._extract_headings(html)

        return WebParseResult(
            uri=base_uri,
            title=title,
            text=text,
            links=links,
            headings=headings,
            parser_provenance={
                "parser": "tool_server.parsers.web_parser.WebParser",
                "version": "1.0.0",
                "method": "regex_heuristic",
                "input_bytes": len(html.encode("utf-8")),
                "output_chars": len(text),
            },
        )

    @staticmethod
    def _extract_title(html: str) -> str | None:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
        # OpenGraph fallback
        m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', html, re.IGNORECASE)
        return m.group(1).strip() if m else None

    @staticmethod
    def _extract_text(html: str) -> str:
        # Strip script/style, then tags, normalize whitespace
        no_script = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", no_script)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _extract_links(html: str, base_uri: str) -> list[str]:
        hrefs = re.findall(r'href=["\'](.*?)["\']', html, re.IGNORECASE)
        absolute = []
        for h in hrefs:
            if h.startswith("http"):
                absolute.append(h)
            elif h.startswith("/"):
                parsed = urllib.parse.urlparse(base_uri)
                absolute.append(f"{parsed.scheme}://{parsed.netloc}{h}")
        return list(dict.fromkeys(absolute))  # deduplicate, preserve order

    @staticmethod
    def _extract_headings(html: str) -> list[str]:
        tags = re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", html, re.IGNORECASE | re.DOTALL)
        cleaned = [re.sub(r"<[^>]+>", "", t).strip() for t in tags]
        return [c for c in cleaned if c]
