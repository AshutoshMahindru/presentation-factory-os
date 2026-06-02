from __future__ import annotations

import json

import pytest

from agents.intake_agent import ChatTurn, IntakeAgent, IntakeUpdateProposal


VALID_RESPONSE = {
    "project_updates": {
        "name": "Atlas Robotics IC memo",
        "audience": "Investment committee",
        "client_name": "Atlas Robotics",
        "decision_required": "Approve Series B investment.",
    },
    "audience_profile": {
        "decision_maker_type": "ic_partner",
        "risk_tolerance": "medium",
        "familiarity_with_topic": "informed",
        "known_objections": ["market_size", "execution_risk"],
        "stakeholder_map": [
            {
                "role": "economic_buyer",
                "concern": "Return profile",
                "influence_level": "high",
            }
        ],
    },
    "confidence": 0.84,
    "gaps": [],
    "recommended_next_action": "Apply the intake updates.",
}


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, float, int]] = []

    def complete(
        self, prompt: str, temperature: float = 0.0, max_tokens: int = 2000
    ) -> str:
        self.calls.append((prompt, temperature, max_tokens))
        return self.response


def test_intake_agent_proposes_valid_structured_update() -> None:
    llm = FakeLLM(json.dumps(VALID_RESPONSE))
    agent = IntakeAgent(llm)

    proposal = agent.propose_updates(
        (
            ChatTurn(role="system", content="internal instruction", turn_index=1),
            ChatTurn(role="user", content="We need an IC memo for Atlas.", turn_index=2),
            ChatTurn(role="assistant", content="Who is the audience?", turn_index=3),
            ChatTurn(role="tool", content="ignored", turn_index=4),
        )
    )

    assert isinstance(proposal, IntakeUpdateProposal)
    assert proposal.project_updates["client_name"] == "Atlas Robotics"
    assert proposal.audience_profile["decision_maker_type"] == "ic_partner"
    assert proposal.confidence == 0.84
    assert proposal.gaps == ()
    assert proposal.ready_for_application is True
    assert llm.calls[0][1] == 0.0
    assert "USER[2]" in llm.calls[0][0]
    assert "ASSISTANT[3]" in llm.calls[0][0]
    assert "TOOL[4]" not in llm.calls[0][0]


def test_intake_agent_accepts_json_code_fence() -> None:
    agent = IntakeAgent(FakeLLM("```json\n" + json.dumps(VALID_RESPONSE) + "\n```"))

    proposal = agent.propose_updates((ChatTurn(role="user", content="hello"),))

    assert proposal.confidence == 0.84


def test_intake_agent_returns_gap_for_empty_history() -> None:
    llm = FakeLLM(json.dumps(VALID_RESPONSE))
    proposal = IntakeAgent(llm).propose_updates(())

    assert proposal.project_updates == {}
    assert proposal.audience_profile == {}
    assert proposal.confidence == 0.0
    assert proposal.ready_for_application is False
    assert proposal.gaps == ("No user or assistant intake chat history is available.",)
    assert llm.calls == []


def test_intake_agent_raises_for_malformed_json() -> None:
    agent = IntakeAgent(FakeLLM("not json"))

    with pytest.raises(ValueError, match="invalid JSON"):
        agent.propose_updates((ChatTurn(role="user", content="hello"),))


def test_intake_agent_raises_for_non_object_json() -> None:
    agent = IntakeAgent(FakeLLM("[]"))

    with pytest.raises(ValueError, match="not an object"):
        agent.propose_updates((ChatTurn(role="user", content="hello"),))


def test_intake_agent_reports_schema_violations_as_gaps() -> None:
    invalid = dict(VALID_RESPONSE)
    invalid["audience_profile"] = {
        "decision_maker_type": "invalid",
        "risk_tolerance": "medium",
        "familiarity_with_topic": "informed",
        "known_objections": [],
        "stakeholder_map": [],
    }
    agent = IntakeAgent(FakeLLM(json.dumps(invalid)))

    proposal = agent.propose_updates((ChatTurn(role="user", content="hello"),))

    assert proposal.ready_for_application is False
    assert proposal.confidence == 0.0
    assert any("audience_profile" in gap for gap in proposal.gaps)
    assert "valid intake update" in proposal.recommended_next_action


def test_intake_update_payload_includes_ready_flag() -> None:
    proposal = IntakeUpdateProposal(
        project_updates={"audience": "IC"},
        audience_profile=VALID_RESPONSE["audience_profile"],
        confidence=0.9,
        gaps=(),
        recommended_next_action="Apply.",
    )

    assert proposal.to_payload()["ready_for_application"] is True
