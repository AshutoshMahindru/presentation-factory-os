from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agents.intake_agent import IntakeAgent
from agents.intake_chat_orchestrator import IntakeChatOrchestrator


VALID_RESPONSE = {
    "project_updates": {
        "audience": "Investment committee",
        "client_name": "Atlas Robotics",
        "decision_required": "Approve Series B investment.",
    },
    "audience_profile": {
        "decision_maker_type": "ic_partner",
        "risk_tolerance": "medium",
        "familiarity_with_topic": "informed",
        "known_objections": ["execution_risk"],
        "stakeholder_map": [
            {
                "role": "economic_buyer",
                "concern": "Return profile",
                "influence_level": "high",
            }
        ],
    },
    "confidence": 0.86,
    "gaps": [],
    "recommended_next_action": "Apply the intake updates.",
}


class FakeWorkflow:
    def __init__(self, messages: tuple[dict[str, Any], ...] = ()) -> None:
        self.messages = list(messages)
        self.append_calls: list[tuple[str, str, str, dict[str, Any] | None, str | None]] = []
        self.list_calls: list[tuple[str, int]] = []

    def append_intake_chat_message(
        self,
        project_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        self.append_calls.append((project_id, role, content, metadata, actor_email))
        message = {
            "message_id": f"message-{len(self.messages) + 1}",
            "project_id": project_id,
            "turn_index": len(self.messages) + 1,
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "actor_email": actor_email,
            "created_at": "2026-06-03T00:00:00+00:00",
        }
        self.messages.append(message)
        return message

    def list_intake_chat_messages(
        self, project_id: str, limit: int = 100
    ) -> tuple[dict[str, Any], ...]:
        self.list_calls.append((project_id, limit))
        return tuple(self.messages[:limit])


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(
        self, prompt: str, temperature: float = 0.0, max_tokens: int = 2000
    ) -> str:
        self.prompts.append(prompt)
        return self.response


def test_orchestrator_appends_user_message_then_assistant_summary() -> None:
    workflow = FakeWorkflow()
    llm = FakeLLM(json.dumps(VALID_RESPONSE))
    orchestrator = IntakeChatOrchestrator(
        workflow_client=workflow,
        intake_agent=IntakeAgent(llm),
    )

    result = orchestrator.handle_user_message(
        project_id="project-1",
        content="We need an IC memo for Atlas Robotics.",
        actor_email="analyst@example.com",
        metadata={"channel": "web"},
    )

    assert result.project_id == "project-1"
    assert result.status == "ready"
    assert result.user_message["role"] == "user"
    assert result.assistant_message is not None
    assert result.assistant_message["role"] == "assistant"
    assert result.source_turn_count == 1
    assert result.proposal.ready_for_application is True
    assert workflow.list_calls == [("project-1", 100)]
    assert len(workflow.append_calls) == 2
    assert workflow.append_calls[0] == (
        "project-1",
        "user",
        "We need an IC memo for Atlas Robotics.",
        {"channel": "web", "source": "intake_chat_orchestrator"},
        "analyst@example.com",
    )
    assistant_call = workflow.append_calls[1]
    assert assistant_call[1] == "assistant"
    assert assistant_call[2] == "Apply the intake updates."
    assert assistant_call[3] is not None
    assert assistant_call[3]["intake_update_proposal"]["ready_for_application"] is True


def test_orchestrator_filters_system_and_tool_history_from_prompt() -> None:
    workflow = FakeWorkflow(
        messages=(
            {
                "role": "system",
                "content": "do not replay",
                "turn_index": 1,
            },
            {
                "role": "tool",
                "content": "internal tool output",
                "turn_index": 2,
            },
            {
                "role": "assistant",
                "content": "Who is the audience?",
                "turn_index": 3,
            },
        )
    )
    llm = FakeLLM(json.dumps(VALID_RESPONSE))
    orchestrator = IntakeChatOrchestrator(workflow, IntakeAgent(llm))

    orchestrator.handle_user_message("project-1", "The IC is the audience.")

    prompt = llm.prompts[0]
    assert "ASSISTANT[3]" in prompt
    assert "USER[4]" in prompt
    assert "do not replay" not in prompt
    assert "internal tool output" not in prompt


def test_orchestrator_rejects_empty_user_message_before_workflow_calls() -> None:
    workflow = FakeWorkflow()
    orchestrator = IntakeChatOrchestrator(
        workflow,
        IntakeAgent(FakeLLM(json.dumps(VALID_RESPONSE))),
    )

    with pytest.raises(ValueError, match="content must not be empty"):
        orchestrator.propose_project_intake_updates("project-1", "   ")

    with pytest.raises(ValueError, match="content must not be empty"):
        orchestrator.handle_user_message("project-1", "   ")

    assert workflow.append_calls == []
    assert workflow.list_calls == []


def test_orchestrator_does_not_append_assistant_on_invalid_llm_json() -> None:
    workflow = FakeWorkflow()
    orchestrator = IntakeChatOrchestrator(workflow, IntakeAgent(FakeLLM("not json")))

    with pytest.raises(ValueError, match="invalid JSON"):
        orchestrator.handle_user_message("project-1", "hello")

    assert len(workflow.append_calls) == 1
    assert workflow.append_calls[0][1] == "user"


def test_orchestrator_payload_shape_is_deterministic() -> None:
    workflow = FakeWorkflow()
    orchestrator = IntakeChatOrchestrator(
        workflow,
        IntakeAgent(FakeLLM(json.dumps(VALID_RESPONSE))),
        history_limit=25,
    )

    payload = orchestrator.handle_user_message(
        "project-1",
        "Need a board update.",
    ).to_payload()

    assert payload == {
        "project_id": "project-1",
        "status": "ready",
        "user_message": {
            "message_id": "message-1",
            "project_id": "project-1",
            "turn_index": 1,
            "role": "user",
            "content": "Need a board update.",
            "metadata": {"source": "intake_chat_orchestrator"},
            "actor_email": None,
            "created_at": "2026-06-03T00:00:00+00:00",
        },
        "assistant_message": {
            "message_id": "message-2",
            "project_id": "project-1",
            "turn_index": 2,
            "role": "assistant",
            "content": "Apply the intake updates.",
            "metadata": {
                "source": "intake_chat_orchestrator",
                "intake_update_proposal": {
                    "project_updates": {
                        "audience": "Investment committee",
                        "client_name": "Atlas Robotics",
                        "decision_required": "Approve Series B investment.",
                    },
                    "audience_profile": VALID_RESPONSE["audience_profile"],
                    "confidence": 0.86,
                    "gaps": [],
                    "recommended_next_action": "Apply the intake updates.",
                    "ready_for_application": True,
                },
            },
            "actor_email": None,
            "created_at": "2026-06-03T00:00:00+00:00",
        },
        "source_turn_count": 1,
        "proposal": {
            "project_updates": {
                "audience": "Investment committee",
                "client_name": "Atlas Robotics",
                "decision_required": "Approve Series B investment.",
            },
            "audience_profile": VALID_RESPONSE["audience_profile"],
            "confidence": 0.86,
            "gaps": [],
            "recommended_next_action": "Apply the intake updates.",
            "ready_for_application": True,
        },
    }
    assert workflow.list_calls == [("project-1", 25)]


def test_orchestrator_validates_positive_history_limit() -> None:
    with pytest.raises(ValueError, match="history_limit must be positive"):
        IntakeChatOrchestrator(FakeWorkflow(), IntakeAgent(FakeLLM("{}")), history_limit=0)


def test_agents_do_not_import_system_chat_repository() -> None:
    for path in [
        Path("agents/intake_agent.py"),
        Path("agents/intake_chat_orchestrator.py"),
    ]:
        text = path.read_text()
        assert "system.chat_repository" not in text
