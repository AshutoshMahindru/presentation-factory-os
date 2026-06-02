from __future__ import annotations

import json
from pathlib import Path

import pytest

from system.chat_repository import ChatMessage, ChatRepository


class FakeResult:
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def message_json(**overrides):
    payload = {
        "message_id": "message-1",
        "project_id": "project-1",
        "turn_index": 1,
        "role": "user",
        "content": "What should the IC care about?",
        "metadata": {"source": "chat"},
        "actor_email": "analyst@example.com",
        "created_at": "2026-06-02T00:00:00+00:00",
    }
    payload.update(overrides)
    return json.dumps(payload, sort_keys=True)


def test_append_message_inserts_next_project_turn() -> None:
    repository = ChatRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult(message_json() + "\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    message = repository.append_message(
        project_id="project-1",
        role="user",
        content="What should the IC care about?",
        metadata={"source": "chat"},
        actor_email="analyst@example.com",
    )

    assert message == ChatMessage(
        message_id="message-1",
        project_id="project-1",
        turn_index=1,
        role="user",
        content="What should the IC care about?",
        metadata={"source": "chat"},
        actor_email="analyst@example.com",
        created_at="2026-06-02T00:00:00+00:00",
    )
    assert "INSERT INTO intake_chat_messages" in captured["sql"]
    assert "pg_advisory_xact_lock" in captured["sql"]
    assert "COALESCE(MAX(turn_index), 0) + 1" in captured["sql"]
    assert "WHERE project_id = 'project-1'" in captured["sql"]
    assert "'analyst@example.com'" in captured["sql"]


def test_append_message_escapes_sql_and_serializes_metadata() -> None:
    repository = ChatRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult(message_json(content="It's urgent") + "\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    repository.append_message(
        project_id="project-'quoted",
        role="assistant",
        content="It's urgent",
        metadata={"b": 2, "a": 1},
    )

    assert "project-''quoted" in captured["sql"]
    assert "It''s urgent" in captured["sql"]
    assert '{"a": 1, "b": 2}' in captured["sql"]
    assert "NULL" in captured["sql"]


def test_append_message_rejects_invalid_role() -> None:
    with pytest.raises(ValueError, match="Unsupported chat role"):
        ChatRepository().append_message("project-1", "critic", "hello")


def test_append_message_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        ChatRepository().append_message("project-1", "user", "   ")


def test_list_messages_returns_project_messages_in_turn_order() -> None:
    repository = ChatRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult(
            "\n".join(
                [
                    message_json(message_id="message-1", turn_index=1, role="user"),
                    message_json(
                        message_id="message-2",
                        turn_index=2,
                        role="assistant",
                        actor_email=None,
                        metadata={"model": "local"},
                    ),
                ]
            )
            + "\n"
        )

    repository._psql = fake_psql  # type: ignore[method-assign]

    messages = repository.list_messages("project-1", limit=50, after_turn_index=1)

    assert [message.message_id for message in messages] == ["message-1", "message-2"]
    assert messages[1].role == "assistant"
    assert messages[1].metadata == {"model": "local"}
    assert messages[1].actor_email is None
    assert "FROM intake_chat_messages" in captured["sql"]
    assert "WHERE project_id = 'project-1'" in captured["sql"]
    assert "AND turn_index > 1" in captured["sql"]
    assert "ORDER BY turn_index ASC" in captured["sql"]
    assert "LIMIT 50" in captured["sql"]


def test_list_messages_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="limit must be between"):
        ChatRepository().list_messages("project-1", limit=0)

    with pytest.raises(ValueError, match="limit must be between"):
        ChatRepository().list_messages("project-1", limit=201)


def test_list_messages_rejects_negative_after_turn_index() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        ChatRepository().list_messages("project-1", after_turn_index=-1)


def test_latest_message_returns_most_recent_turn() -> None:
    repository = ChatRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult(message_json(message_id="message-3", turn_index=3) + "\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    message = repository.latest_message("project-1")

    assert message is not None
    assert message.message_id == "message-3"
    assert message.turn_index == 3
    assert "ORDER BY turn_index DESC" in captured["sql"]
    assert "LIMIT 1" in captured["sql"]


def test_latest_message_returns_none_without_rows() -> None:
    repository = ChatRepository()

    def fake_psql(sql: str) -> FakeResult:
        return FakeResult("")

    repository._psql = fake_psql  # type: ignore[method-assign]

    assert repository.latest_message("project-1") is None


def test_repository_raises_on_psql_failure() -> None:
    repository = ChatRepository()

    def fake_psql(sql: str) -> FakeResult:
        return FakeResult(returncode=1, stderr="database down")

    repository._psql = fake_psql  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="database down"):
        repository.list_messages("project-1")


def test_canonical_schema_defines_intake_chat_messages() -> None:
    schema = Path("docs/04_Database_Schemas.sql").read_text()

    assert "CREATE TABLE IF NOT EXISTS intake_chat_messages" in schema
    assert "project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE" in schema
    assert "UNIQUE(project_id, turn_index)" in schema
    assert "CHECK (role IN ('user', 'assistant', 'system', 'tool'))" in schema
    assert "idx_intake_chat_project_turn" in schema
    assert "idx_intake_chat_project_created" in schema
