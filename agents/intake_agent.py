from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from jsonschema import Draft202012Validator


AUDIENCE_PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "decision_maker_type",
        "risk_tolerance",
        "familiarity_with_topic",
        "known_objections",
        "stakeholder_map",
    ],
    "properties": {
        "decision_maker_type": {
            "type": "string",
            "enum": ["ic_partner", "cfo", "ceo", "board", "technical_lead"],
        },
        "risk_tolerance": {"type": "string", "enum": ["low", "medium", "high"]},
        "familiarity_with_topic": {
            "type": "string",
            "enum": ["novice", "informed", "expert"],
        },
        "known_objections": {
            "type": "array",
            "minItems": 0,
            "items": {
                "type": "string",
                "enum": [
                    "pricing",
                    "timing",
                    "team_risk",
                    "market_size",
                    "execution_risk",
                    "technical_risk",
                    "regulatory_risk",
                    "capital_intensity",
                    "competitive_position",
                ],
            },
        },
        "stakeholder_map": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["role", "concern"],
                "properties": {
                    "role": {
                        "type": "string",
                        "enum": [
                            "economic_buyer",
                            "technical_evaluator",
                            "risk_owner",
                            "sponsor",
                            "blocker",
                            "influencer",
                        ],
                    },
                    "concern": {"type": "string", "minLength": 1},
                    "influence_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
            },
        },
    },
}


INTAKE_UPDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "project_updates",
        "audience_profile",
        "confidence",
        "gaps",
        "recommended_next_action",
    ],
    "properties": {
        "project_updates": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "audience": {"type": "string", "minLength": 1},
                "client_name": {"type": "string", "minLength": 1},
                "decision_required": {"type": "string", "minLength": 1},
            },
        },
        "audience_profile": AUDIENCE_PROFILE_SCHEMA,
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "gaps": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "recommended_next_action": {"type": "string", "minLength": 1},
    },
}


class LLMClient(Protocol):
    def complete(
        self, prompt: str, temperature: float = 0.0, max_tokens: int = 2000
    ) -> str:
        ...


@dataclass(frozen=True)
class ChatTurn:
    role: str
    content: str
    turn_index: int | None = None


@dataclass(frozen=True)
class IntakeUpdateProposal:
    project_updates: dict[str, str]
    audience_profile: dict[str, Any]
    confidence: float
    gaps: tuple[str, ...]
    recommended_next_action: str

    @property
    def ready_for_application(self) -> bool:
        return self.confidence >= 0.75 and not self.gaps

    def to_payload(self) -> dict[str, Any]:
        return {
            "project_updates": self.project_updates,
            "audience_profile": self.audience_profile,
            "confidence": self.confidence,
            "gaps": list(self.gaps),
            "recommended_next_action": self.recommended_next_action,
            "ready_for_application": self.ready_for_application,
        }


class IntakeAgent:
    """Derive structured intake updates from a bounded chat transcript."""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client
        self._update_validator = Draft202012Validator(INTAKE_UPDATE_SCHEMA)

    def propose_updates(self, turns: tuple[ChatTurn, ...]) -> IntakeUpdateProposal:
        relevant_turns = self._filter_user_and_assistant_turns(turns)
        if not relevant_turns:
            return IntakeUpdateProposal(
                project_updates={},
                audience_profile={},
                confidence=0.0,
                gaps=("No user or assistant intake chat history is available.",),
                recommended_next_action="Ask the operator for intake context.",
            )

        raw = self.llm.complete(
            self._build_prompt(relevant_turns),
            temperature=0.0,
            max_tokens=1800,
        )
        data = self._parse_json_object(raw)
        errors = tuple(
            sorted(
                self._format_schema_error(error)
                for error in self._update_validator.iter_errors(data)
            )
        )
        if errors:
            return IntakeUpdateProposal(
                project_updates={},
                audience_profile={},
                confidence=0.0,
                gaps=errors,
                recommended_next_action="Ask the model to return a valid intake update JSON object.",
            )

        return IntakeUpdateProposal(
            project_updates={
                key: str(value)
                for key, value in data["project_updates"].items()
                if value is not None
            },
            audience_profile=dict(data["audience_profile"]),
            confidence=round(float(data["confidence"]), 3),
            gaps=tuple(str(gap) for gap in data["gaps"]),
            recommended_next_action=str(data["recommended_next_action"]),
        )

    def _filter_user_and_assistant_turns(
        self, turns: tuple[ChatTurn, ...]
    ) -> tuple[ChatTurn, ...]:
        return tuple(turn for turn in turns if turn.role in {"user", "assistant"})

    def _build_prompt(self, turns: tuple[ChatTurn, ...]) -> str:
        transcript = "\n".join(
            f"{turn.role.upper()}[{turn.turn_index or '?'}]: {turn.content}"
            for turn in turns
        )
        return (
            "Convert the following PFOS intake chat transcript into exactly one JSON object.\n"
            "Return no markdown.\n"
            "Required keys: project_updates, audience_profile, confidence, gaps, recommended_next_action.\n"
            "project_updates may include name, audience, client_name, decision_required.\n"
            "audience_profile must match the PFOS AudienceProfile schema.\n\n"
            f"Transcript:\n{transcript}"
        )

    def _parse_json_object(self, raw: str) -> dict[str, Any]:
        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = self._strip_code_fence(stripped)

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

        if not isinstance(parsed, dict):
            raise ValueError("LLM returned JSON that is not an object")
        return parsed

    def _strip_code_fence(self, value: str) -> str:
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def _format_schema_error(self, error: Any) -> str:
        path = ".".join(str(part) for part in error.path) or "<root>"
        return f"{path}: {error.message}"
