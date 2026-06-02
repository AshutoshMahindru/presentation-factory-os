from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from agents.intake_agent import ChatTurn, IntakeAgent, IntakeUpdateProposal


class WorkflowClient(Protocol):
    def append_intake_chat_message(
        self,
        project_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        ...

    def list_intake_chat_messages(
        self, project_id: str, limit: int = 100
    ) -> tuple[dict[str, Any], ...]:
        ...


@dataclass(frozen=True)
class IntakeOrchestrationResult:
    project_id: str
    status: str
    user_message: dict[str, Any]
    assistant_message: dict[str, Any] | None
    source_turn_count: int
    proposal: IntakeUpdateProposal

    def to_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "status": self.status,
            "user_message": self.user_message,
            "assistant_message": self.assistant_message,
            "source_turn_count": self.source_turn_count,
            "proposal": self.proposal.to_payload(),
        }


class IntakeChatOrchestrator:
    """Coordinate Step 113 intake chat history into structured update proposals."""

    def __init__(
        self,
        workflow_client: WorkflowClient,
        intake_agent: IntakeAgent,
        history_limit: int = 100,
    ) -> None:
        if history_limit <= 0:
            raise ValueError("history_limit must be positive")
        self.workflow = workflow_client
        self.intake_agent = intake_agent
        self.history_limit = history_limit

    def handle_user_message(
        self,
        project_id: str,
        content: str,
        actor_email: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IntakeOrchestrationResult:
        if not content.strip():
            raise ValueError("content must not be empty")

        user_message = self.workflow.append_intake_chat_message(
            project_id=project_id,
            role="user",
            content=content,
            metadata={
                **(metadata or {}),
                "source": "intake_chat_orchestrator",
            },
            actor_email=actor_email,
        )
        messages = self.workflow.list_intake_chat_messages(
            project_id=project_id,
            limit=self.history_limit,
        )
        turns = tuple(self._turn_from_message(message) for message in messages)
        proposal = self.intake_agent.propose_updates(turns)
        assistant_message = self.workflow.append_intake_chat_message(
            project_id=project_id,
            role="assistant",
            content=proposal.recommended_next_action,
            metadata={
                "source": "intake_chat_orchestrator",
                "intake_update_proposal": proposal.to_payload(),
            },
        )
        return IntakeOrchestrationResult(
            project_id=project_id,
            status="ready" if proposal.ready_for_application else "needs_input",
            user_message=user_message,
            assistant_message=assistant_message,
            source_turn_count=len(turns),
            proposal=proposal,
        )

    def propose_project_intake_updates(
        self,
        project_id: str,
        user_message: str,
        actor_email: str | None = None,
    ) -> IntakeOrchestrationResult:
        return self.handle_user_message(
            project_id=project_id,
            content=user_message,
            actor_email=actor_email,
        )

    def _turn_from_message(self, message: dict[str, Any]) -> ChatTurn:
        role = str(message.get("role", ""))
        content = str(message.get("content", ""))
        turn_index = message.get("turn_index")
        if turn_index is not None:
            turn_index = int(turn_index)
        return ChatTurn(
            role=role,
            content=content,
            turn_index=turn_index,
        )
