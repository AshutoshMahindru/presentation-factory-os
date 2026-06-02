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


class ThesisInitiationMixin:
    """Mixin for ResearchAgent thesis generation."""

    def generate_thesis_v0(self, project_id: str, topic: str, selected_persona: dict | None = None) -> dict[str, Any]:
        prompt = self._build_thesis_prompt(topic, selected_persona)
        raw = self.llm.complete(prompt, temperature=0.0, max_tokens=2500)

        json_str = self._extract_json(raw)
        data = json.loads(json_str)
        self._validate_json_schema(data, THESIS_SCHEMA)

        if len(data["pillars"]) > 10:
            raise ValueError(f"Too many pillars: {len(data['pillars'])} (max 10)")
        if len(set(p["statement"] for p in data["pillars"])) != len(data["pillars"]):
            raise ValueError("Duplicate pillar statements detected")

        # Submit through workflow API
        payload = {
            "project_id": project_id,
            "thesis_statement": data["thesis_statement"],
            "pillars": data["pillars"],
        }
        result = self.workflow.create_thesis_version(project_id, payload)
        return {"thesis_version_id": result["id"], "pillars_count": len(data["pillars"])}

    @staticmethod
    def _build_thesis_prompt(topic: str, persona: dict | None) -> str:
        persona_hint = ""
        if persona:
            persona_hint = (
                f"\nAudience: {persona.get('title', 'General')}. "
                f"Time budget: {persona.get('time_budget_minutes', 10)} minutes. "
                f"Tone: {persona.get('tone', 'neutral')}."
            )
        return (
            f"Generate an investment thesis on: {topic}{persona_hint}\n"
            f"Return exactly one JSON object with:\n"
            f"  thesis_statement: concise declarative sentence (max 500 chars)\n"
            f"  pillars: array of 3-10 supporting arguments, each with pillar_index, pillar_type, statement\n"
            f"Pillar types: claim, data, objection, narrative, financial.\n"
            f"No markdown, only raw JSON."
        )


class ResearchLoopMixin:
    """Mixin for ResearchAgent unbounded research loop."""

    EPSILON = 0.05  # convergence threshold

    def run_research_loop(
        self,
        project_id: str,
        topic: str,
        max_loops: int | None = None,  # None = unbounded; operator can force stop
        financial_agent: Any | None = None,  # optional FinancialAgent for step 111
    ) -> dict[str, Any]:
        loop_number = 1
        previous_thesis = None
        last_real_thesis_id: str | None = None  # track the actual thesis id

        while True:
            # Start loop audit
            # Discover sources
            source_ids = self.discover_and_register_sources(project_id, topic, max_sources=10)

            # Generate or refine thesis
            if loop_number == 1:
                result = self.generate_thesis_v0(project_id, topic)
                # Capture the real thesis id so subsequent stub iterations
                # can still pass it to the financial review endpoint.
                thesis_id = result.get("thesis_version_id")
                if thesis_id:
                    last_real_thesis_id = str(thesis_id)
            else:
                # In v3.3.0: deep-read and refine; for now, stub iteration
                result = {
                    "thesis_version_id": last_real_thesis_id,
                    "pillars_count": 0,
                }

            # Step 111: financial review of the generated thesis. The
            # review can mark pillars as stressed (contradiction) and the
            # stressed count feeds into convergence so a thesis with
            # contradicting financial cells takes longer to converge.
            stressed_pillar_count = 0
            thesis_version_id = result.get("thesis_version_id")
            if financial_agent is not None and thesis_version_id:
                review = financial_agent.review_sources_for_pillars(
                    project_id=project_id, thesis_version_id=thesis_version_id
                ) if hasattr(financial_agent, "review_sources_for_pillars") else \
                    financial_agent.review_sources_for_thesis(
                        project_id=project_id, thesis_version_id=thesis_version_id
                    )
                stressed_pillar_count = len(review.pillars_with_contradictions())
                # Mark each contradicting pillar as stressed in the thesis
                # repository so downstream gates (step 112) can see them.
                for pillar_id in review.pillars_with_contradictions():
                    self._mark_pillar_stressed(thesis_version_id, pillar_id)

            # Evaluate convergence. The stub delta is reduced when there
            # are no stressed pillars and increased when there are.
            current = type("_StubThesis", (), {"id": "stub-thesis"})() if loop_number > 1 else None
            delta = self.evaluate_convergence(previous_thesis, current, stressed_pillar_count)

            # Finalize loop
            loop_id = self._start_loop_record(project_id, loop_number, len(source_ids))
            self._finalize_loop_record(loop_id, delta, len(source_ids), "converged" if delta < self.EPSILON else "running")

            if delta < self.EPSILON:
                return {
                    "status": "converged",
                    "loops": loop_number,
                    "thesis_version_id": str(current.id) if current else None,
                    "convergence_delta": delta,
                    "stressed_pillar_count": stressed_pillar_count,
                }

            if max_loops is not None and loop_number >= max_loops:
                return {
                    "status": "max_loops_reached",
                    "loops": loop_number,
                    "thesis_version_id": str(current.id) if current else None,
                    "convergence_delta": delta,
                    "stressed_pillar_count": stressed_pillar_count,
                }

            previous_thesis = str(current.id) if current else None
            loop_number += 1

    def evaluate_convergence(
        self,
        previous_thesis_id: str | None,
        current_thesis: Any,
        stressed_pillar_count: int = 0,
    ) -> float:
        if previous_thesis_id is None or current_thesis is None:
            # First loop: no financial review yet, so the convergence
            # delta is high.
            return 1.0
        # Stub: base delta drops below EPSILON when there are no stressed
        # pillars; with stressed pillars the delta is bumped up to keep
        # the loop running so the operator can address the contradiction.
        base = 0.03
        if stressed_pillar_count > 0:
            return base + 0.10 * stressed_pillar_count
        return base

    def _start_loop_record(self, project_id: str, loop_number: int, discovered: int) -> str:
        # Call workflow API to start research loop
        payload = {
            "project_id": project_id,
            "loop_number": loop_number,
            "sources_discovered_count": discovered,
        }
        result = self.workflow._post("/research-loops/start", payload)
        return result.get("id", "loop-stub")

    def _finalize_loop_record(
        self,
        loop_id: str,
        delta: float,
        discovered: int,
        status: str,
    ) -> None:
        payload = {
            "convergence_delta": delta,
            "sources_discovered_count": discovered,
            "status": status,
        }
        self.workflow._post(f"/research-loops/{loop_id}/finalize", payload)

    def _mark_pillar_stressed(
        self, thesis_version_id: str, pillar_id: str
    ) -> None:
        """Mark a pillar as stressed after a financial contradiction.

        Thin wrapper over the thesis-repository's mark_pillar_stressed
        method, invoked via the workflow API so the agent stays
        DB-import-free.
        """
        try:
            self.workflow._post(  # type: ignore[attr-defined]
                f"/thesis-versions/{thesis_version_id}/pillars/{pillar_id}/stress",
                {"stress_status": "stressed"},
            )
        except Exception:
            # The stress endpoint is added in a follow-up step; for now,
            # treat the mark as a no-op so the loop can run end-to-end
            # even before the endpoint lands.
            pass


class ResearchAgent(BaseAgent, ThesisInitiationMixin, ResearchLoopMixin):
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


# --- Step 105: Thesis Initiation ---

THESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "thesis_statement": {"type": "string", "maxLength": 500},
        "pillars": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "properties": {
                    "pillar_index": {"type": "integer"},
                    "pillar_type": {"type": "string", "enum": ["claim", "data", "objection", "narrative", "financial"]},
                    "statement": {"type": "string", "maxLength": 300}
                },
                "required": ["pillar_index", "pillar_type", "statement"]
            }
        }
    },
    "required": ["thesis_statement", "pillars"]
}


# --- Step 106: Iterative Research Loop Core ---
