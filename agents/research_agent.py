from __future__ import annotations

import json
from urllib.parse import urlparse
from typing import Any
from uuid import UUID

from agents.base_agent import BaseAgent, WorkflowClient, LLMClient


SOURCE_PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "uri": {"type": "string"},
                    "title": {"type": "string"},
                    "source_type": {"type": "string", "enum": ["pdf", "web", "document"]},
                    "summary": {"type": "string"}
                },
                "required": ["uri", "source_type"]
            },
            "maxItems": 10
        }
    },
    "required": ["sources"]
}


class ResearchAgent(BaseAgent):
    def __init__(
        self,
        workflow_client: WorkflowClient | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.workflow = workflow_client or WorkflowClient()
        self.llm = llm_client or LLMClient()

    def discover_and_register_sources(
        self,
        project_id: str,
        topic: str,
        max_sources: int = 10,
    ) -> list[str]:
        prompt = self._build_discovery_prompt(topic, max_sources)
        raw = self.llm.complete(prompt, temperature=0.0, max_tokens=2000)

        json_str = self._extract_json(raw)
        data = json.loads(json_str)
        self._validate_json_schema(data, SOURCE_PROPOSAL_SCHEMA)

        registered_ids: list[str] = []
        for src in data["sources"]:
            if not self._is_valid_uri(src["uri"]):
                continue

            payload = {
                "uri": src["uri"],
                "title": src.get("title"),
                "source_type": src["source_type"],
                "normalized_text": src.get("summary", "")[:5000],
            }
            result = self.workflow.create_source(project_id, payload)
            registered_ids.append(result["id"])

        return registered_ids

    @staticmethod
    def _build_discovery_prompt(topic: str, max_sources: int) -> str:
        return (
            f"You are a research assistant finding authoritative sources on: {topic}\n"
            f"Return exactly one JSON object with a 'sources' array (max {max_sources} items). "
            f"Each source must have: uri (valid http/https URL), title, source_type (pdf/web/document), summary. "
            f"Do not include markdown formatting, only raw JSON."
        )

    @staticmethod
    def _extract_json(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        return text

    @staticmethod
    def _is_valid_uri(uri: str) -> bool:
        parsed = urlparse(uri)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
