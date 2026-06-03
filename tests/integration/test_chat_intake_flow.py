from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

import api.workflow as workflow
from agents.intake_agent import IntakeAgent
from agents.intake_chat_orchestrator import IntakeChatOrchestrator
from system.chat_repository import ChatMessage


client = TestClient(workflow.app)
API_MEDIA_TYPE = "application/vnd.pfos.v3.2.4+json"


READY_RESPONSE = {
    "project_updates": {
        "audience": "Investment committee",
        "client_name": "Atlas Robotics",
        "decision_required": "Approve the Series B investment.",
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


NEEDS_INPUT_RESPONSE = {
    "project_updates": {},
    "audience_profile": {
        "decision_maker_type": "ic_partner",
        "risk_tolerance": "medium",
        "familiarity_with_topic": "informed",
        "known_objections": [],
        "stakeholder_map": [
            {
                "role": "economic_buyer",
                "concern": "Audience not fully qualified",
                "influence_level": "medium",
            }
        ],
    },
    "confidence": 0.42,
    "gaps": ["Confirm the decision required and primary audience."],
    "recommended_next_action": "Ask for the decision required and audience.",
}


class FakeProjectRepository:
    def __init__(self) -> None:
        self.project = SimpleNamespace(
            project_id="project-1",
            name="Original name",
            audience="Original audience",
            audience_profile={"original": True},
            current_phase="intake",
        )

    def get_project(self, project_id: str):
        return self.project if project_id == self.project.project_id else None


class InMemoryChatRepository:
    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []

    def append_message(
        self,
        project_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        actor_email: str | None = None,
    ) -> ChatMessage:
        if not content.strip():
            raise ValueError("Chat message content must not be empty")

        message = ChatMessage(
            message_id=f"message-{len(self.messages) + 1}",
            project_id=project_id,
            turn_index=len(self.messages) + 1,
            role=role,
            content=content,
            metadata=metadata or {},
            actor_email=actor_email,
            created_at="2026-06-03T00:00:00+00:00",
        )
        self.messages.append(message)
        return message

    def list_messages(
        self,
        project_id: str,
        limit: int = 100,
        after_turn_index: int | None = None,
    ) -> tuple[ChatMessage, ...]:
        selected = [
            message
            for message in self.messages
            if message.project_id == project_id
            and (after_turn_index is None or message.turn_index > after_turn_index)
        ]
        return tuple(selected[:limit])


class SequencedLLM:
    def __init__(self, responses: tuple[dict[str, Any], ...] | tuple[str, ...]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def complete(
        self, prompt: str, temperature: float = 0.0, max_tokens: int = 2000
    ) -> str:
        self.prompts.append(prompt)
        response = self.responses.pop(0)
        if isinstance(response, str):
            return response
        return json.dumps(response)


def install_intake_flow(monkeypatch, llm: SequencedLLM):
    project_repository = FakeProjectRepository()
    chat_repository = InMemoryChatRepository()
    monkeypatch.setattr(workflow, "project_repository", project_repository)
    monkeypatch.setattr(workflow, "chat_repository", chat_repository)
    monkeypatch.setattr(
        workflow,
        "intake_chat_orchestrator",
        IntakeChatOrchestrator(
            workflow_client=workflow.WorkflowChatClient(chat_repository),
            intake_agent=IntakeAgent(llm),
        ),
    )
    return project_repository, chat_repository


def test_intake_chat_post_appends_user_and_assistant_then_get_lists_transcript(
    monkeypatch,
) -> None:
    _, chat_repository = install_intake_flow(
        monkeypatch,
        SequencedLLM((NEEDS_INPUT_RESPONSE, READY_RESPONSE)),
    )

    first = client.post(
        "/projects/project-1/intake-chat",
        json={
            "content": "We need a Series B IC memo.",
            "actor_email": "analyst@example.com",
            "metadata": {"channel": "web"},
        },
    )
    second = client.post(
        "/projects/project-1/intake-chat/messages",
        json={"content": "Audience is the investment committee."},
    )
    transcript = client.get("/projects/project-1/intake-chat/messages")

    assert first.status_code == 200
    assert first.json()["status"] == "needs_input"
    assert second.status_code == 200
    assert second.json()["status"] == "ready"
    assert transcript.status_code == 200
    payload = transcript.json()
    assert payload["message_count"] == 4
    assert [message["role"] for message in payload["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert [message["turn_index"] for message in payload["messages"]] == [1, 2, 3, 4]
    assert payload["messages"][0]["actor_email"] == "analyst@example.com"
    assert payload["messages"][0]["metadata"] == {
        "channel": "web",
        "source": "intake_chat_orchestrator",
    }
    assert payload["messages"][1]["metadata"]["intake_update_proposal"][
        "ready_for_application"
    ] is False
    assert chat_repository.messages[-1].content == "Apply the intake updates."


def test_intake_chat_invalid_llm_json_persists_only_user_turn(monkeypatch) -> None:
    _, chat_repository = install_intake_flow(
        monkeypatch,
        SequencedLLM(("not json",)),
    )

    response = client.post(
        "/projects/project-1/intake-chat",
        json={"content": "Start an IC memo."},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_chat_message"
    assert [message.role for message in chat_repository.messages] == ["user"]


def test_intake_chat_proposal_does_not_mutate_project_fields(monkeypatch) -> None:
    project_repository, _ = install_intake_flow(
        monkeypatch,
        SequencedLLM((READY_RESPONSE,)),
    )

    response = client.post(
        "/projects/project-1/intake-chat",
        json={"content": "Atlas Robotics needs Series B approval."},
        headers={"Accept": API_MEDIA_TYPE, "Content-Type": API_MEDIA_TYPE},
    )

    assert response.status_code == 200
    assert response.json()["proposal"]["project_updates"] == {
        "audience": "Investment committee",
        "client_name": "Atlas Robotics",
        "decision_required": "Approve the Series B investment.",
    }
    assert project_repository.project.name == "Original name"
    assert project_repository.project.audience == "Original audience"
    assert project_repository.project.audience_profile == {"original": True}
