from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

import api.workflow as workflow
from system.chat_repository import ChatMessage


client = TestClient(workflow.app)


def chat_message(
    *,
    message_id: str,
    project_id: str = "project-1",
    turn_index: int = 1,
    role: str = "user",
    content: str = "Need an IC memo for Atlas Robotics.",
    metadata: dict[str, Any] | None = None,
    actor_email: str | None = "analyst@example.com",
) -> ChatMessage:
    return ChatMessage(
        message_id=message_id,
        project_id=project_id,
        turn_index=turn_index,
        role=role,
        content=content,
        metadata=metadata or {},
        actor_email=actor_email,
        created_at="2026-06-03T00:00:00+00:00",
    )


class FakeProjectRepository:
    def __init__(self, phase: str | None = "intake") -> None:
        self.phase = phase

    def get_project(self, project_id: str):
        if self.phase is None:
            return None
        return SimpleNamespace(project_id=project_id, current_phase=self.phase)


class FakeChatRepository:
    def __init__(self, messages: tuple[ChatMessage, ...]) -> None:
        self.messages = messages
        self.calls: list[tuple[str, int, int | None]] = []

    def list_messages(
        self,
        project_id: str,
        limit: int = 100,
        after_turn_index: int | None = None,
    ) -> tuple[ChatMessage, ...]:
        self.calls.append((project_id, limit, after_turn_index))
        selected = [
            message
            for message in self.messages
            if after_turn_index is None or message.turn_index > after_turn_index
        ]
        return tuple(selected[:limit])


@dataclass(frozen=True)
class FakeOrchestrationResult:
    payload: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return self.payload


class FakeOrchestrator:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response
        self.calls: list[tuple[str, str, str | None, dict[str, Any] | None]] = []

    def handle_user_message(
        self,
        project_id: str,
        content: str,
        actor_email: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FakeOrchestrationResult:
        self.calls.append((project_id, content, actor_email, metadata))
        if self.response is None:
            raise ValueError("invalid intake content")
        return FakeOrchestrationResult(self.response)


def turn_payload() -> dict[str, Any]:
    user = workflow.chat_message_to_payload(chat_message(message_id="message-1"))
    assistant = workflow.chat_message_to_payload(
        chat_message(
            message_id="message-2",
            turn_index=2,
            role="assistant",
            content="Continue intake chat before applying project updates.",
            metadata={
                "source": "intake_chat_orchestrator",
                "intake_update_proposal": {"ready_for_application": False},
            },
            actor_email=None,
        )
    )
    return {
        "project_id": "project-1",
        "status": "needs_input",
        "user_message": user,
        "assistant_message": assistant,
        "source_turn_count": 1,
        "proposal": {
            "project_updates": {},
            "audience_profile": {},
            "confidence": 0.2,
            "gaps": ["More context is required."],
            "recommended_next_action": (
                "Continue intake chat before applying project updates."
            ),
            "ready_for_application": False,
        },
    }


def test_get_intake_chat_unknown_project_returns_404(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "project_repository", FakeProjectRepository(None))

    response = client.get("/projects/missing-project/intake-chat/messages")

    assert response.status_code == 404
    assert response.json()["detail"] == {"error": "project_not_found"}


def test_get_intake_chat_returns_ordered_messages_and_filters_after_turn(
    monkeypatch,
) -> None:
    messages = (
        chat_message(message_id="message-1", turn_index=1, role="user"),
        chat_message(
            message_id="message-2",
            turn_index=2,
            role="assistant",
            actor_email=None,
        ),
        chat_message(message_id="message-3", turn_index=3, role="user"),
    )
    fake_chat = FakeChatRepository(messages)
    monkeypatch.setattr(workflow, "project_repository", FakeProjectRepository())
    monkeypatch.setattr(workflow, "chat_repository", fake_chat)

    response = client.get(
        "/projects/project-1/intake-chat/messages",
        params={"limit": 10, "after_turn_index": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "project-1"
    assert payload["message_count"] == 2
    assert [message["turn_index"] for message in payload["messages"]] == [2, 3]
    assert fake_chat.calls == [("project-1", 10, 1)]


def test_get_intake_chat_rejects_invalid_query_bounds(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "project_repository", FakeProjectRepository())

    limit_response = client.get(
        "/projects/project-1/intake-chat/messages",
        params={"limit": 0},
    )
    after_response = client.get(
        "/projects/project-1/intake-chat/messages",
        params={"after_turn_index": -1},
    )

    assert limit_response.status_code == 422
    assert limit_response.json()["detail"]["error"] == "invalid_chat_query"
    assert after_response.status_code == 422
    assert after_response.json()["detail"]["error"] == "invalid_chat_query"


def test_post_intake_chat_unknown_project_returns_404(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "project_repository", FakeProjectRepository(None))

    response = client.post(
        "/projects/missing-project/intake-chat/messages",
        json={"content": "Start intake."},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {"error": "project_not_found"}


def test_post_intake_chat_rejects_non_intake_phase(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "project_repository", FakeProjectRepository("created"))

    response = client.post(
        "/projects/project-1/intake-chat/messages",
        json={"content": "Start intake."},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "error": "phase_mismatch",
        "current_phase": "created",
        "required_phase": "intake",
    }


def test_post_intake_chat_delegates_to_orchestrator(monkeypatch) -> None:
    fake_orchestrator = FakeOrchestrator(turn_payload())
    monkeypatch.setattr(workflow, "project_repository", FakeProjectRepository())
    monkeypatch.setattr(workflow, "intake_chat_orchestrator", fake_orchestrator)

    response = client.post(
        "/projects/project-1/intake-chat/messages",
        json={
            "content": "Need an IC memo for Atlas Robotics.",
            "actor_email": "analyst@example.com",
            "metadata": {"channel": "web"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_input"
    assert payload["user_message"]["role"] == "user"
    assert payload["assistant_message"]["role"] == "assistant"
    assert payload["proposal"]["gaps"] == ["More context is required."]
    assert fake_orchestrator.calls == [
        (
            "project-1",
            "Need an IC memo for Atlas Robotics.",
            "analyst@example.com",
            {"channel": "web"},
        )
    ]


def test_post_intake_chat_maps_orchestrator_value_error_to_422(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "project_repository", FakeProjectRepository())
    monkeypatch.setattr(workflow, "intake_chat_orchestrator", FakeOrchestrator(None))

    response = client.post(
        "/projects/project-1/intake-chat/messages",
        json={"content": "Start intake."},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "error": "invalid_chat_message",
        "message": "invalid intake content",
    }
