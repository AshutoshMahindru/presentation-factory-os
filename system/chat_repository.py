from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from system.db import execute_psql


@dataclass(frozen=True)
class ChatMessage:
    message_id: str
    project_id: str
    turn_index: int
    role: str
    content: str
    metadata: dict[str, Any]
    actor_email: str | None
    created_at: str


class ChatRepository:
    ALLOWED_ROLES = {"user", "assistant", "system", "tool"}
    MAX_LIST_LIMIT = 200

    def append_message(
        self,
        project_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        actor_email: str | None = None,
    ) -> ChatMessage:
        if role not in self.ALLOWED_ROLES:
            raise ValueError(f"Unsupported chat role: {role}")

        if not content.strip():
            raise ValueError("Chat message content must not be empty")

        metadata_json = self._json(metadata or {})
        actor_email_sql = self._nullable(actor_email)
        project_id_sql = self._sql(project_id)

        sql = f"""
        BEGIN;
        SELECT pg_advisory_xact_lock(hashtext('intake_chat_messages:{project_id_sql}'));

        WITH next_turn AS (
          SELECT COALESCE(MAX(turn_index), 0) + 1 AS turn_index
          FROM intake_chat_messages
          WHERE project_id = '{project_id_sql}'
        ),
        inserted AS (
          INSERT INTO intake_chat_messages (
            project_id,
            turn_index,
            role,
            content,
            metadata,
            actor_email
          )
          SELECT
            '{project_id_sql}',
            next_turn.turn_index,
            '{self._sql(role)}',
            '{self._sql(content)}',
            '{metadata_json}'::jsonb,
            {actor_email_sql}
          FROM next_turn
          RETURNING id, project_id, turn_index, role, content, metadata, actor_email, created_at
        )
        SELECT json_build_object(
          'message_id', id,
          'project_id', project_id,
          'turn_index', turn_index,
          'role', role,
          'content', content,
          'metadata', metadata,
          'actor_email', actor_email,
          'created_at', created_at
        )::text
        FROM inserted;
        COMMIT;
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        return self._parse_message_result(result.stdout)

    def list_messages(
        self,
        project_id: str,
        limit: int = 100,
        after_turn_index: int | None = None,
    ) -> tuple[ChatMessage, ...]:
        if limit <= 0 or limit > self.MAX_LIST_LIMIT:
            raise ValueError(f"limit must be between 1 and {self.MAX_LIST_LIMIT}")

        after_filter = ""
        if after_turn_index is not None:
            if after_turn_index < 0:
                raise ValueError("after_turn_index must be non-negative")
            after_filter = f"AND turn_index > {after_turn_index}"

        sql = f"""
        SELECT json_build_object(
          'message_id', id,
          'project_id', project_id,
          'turn_index', turn_index,
          'role', role,
          'content', content,
          'metadata', metadata,
          'actor_email', actor_email,
          'created_at', created_at
        )::text
        FROM intake_chat_messages
        WHERE project_id = '{self._sql(project_id)}'
        {after_filter}
        ORDER BY turn_index ASC
        LIMIT {limit};
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        return tuple(
            self._message_from_json(line)
            for line in result.stdout.splitlines()
            if line.strip()
        )

    def latest_message(self, project_id: str) -> ChatMessage | None:
        sql = f"""
        SELECT json_build_object(
          'message_id', id,
          'project_id', project_id,
          'turn_index', turn_index,
          'role', role,
          'content', content,
          'metadata', metadata,
          'actor_email', actor_email,
          'created_at', created_at
        )::text
        FROM intake_chat_messages
        WHERE project_id = '{self._sql(project_id)}'
        ORDER BY turn_index DESC
        LIMIT 1;
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        for line in result.stdout.splitlines():
            if line.strip():
                return self._message_from_json(line)
        return None

    def _parse_message_result(self, stdout: str) -> ChatMessage:
        for line in stdout.splitlines():
            if line.strip().startswith("{"):
                return self._message_from_json(line)
        raise RuntimeError(f"Unexpected chat message result: {stdout!r}")

    def _message_from_json(self, line: str) -> ChatMessage:
        data = json.loads(line)
        return ChatMessage(
            message_id=str(data["message_id"]),
            project_id=str(data["project_id"]),
            turn_index=int(data["turn_index"]),
            role=str(data["role"]),
            content=str(data["content"]),
            metadata=dict(data.get("metadata") or {}),
            actor_email=data.get("actor_email"),
            created_at=str(data["created_at"]),
        )

    def _psql(self, sql: str):
        return execute_psql(sql)

    def _json(self, value: dict[str, Any]) -> str:
        return self._sql(json.dumps(value, sort_keys=True))

    def _nullable(self, value: str | None) -> str:
        if value is None:
            return "NULL"
        return f"'{self._sql(value)}'"

    def _sql(self, value: str) -> str:
        return value.replace("'", "''")
