from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from system.source_register_repository import SourceRegisterRepository


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> dict[str, Any] | None:
        # Step 107: update_search_coverage uses an UPDATE; the test only
        # needs to assert the SQL was issued, not the result.
        return None


class _FakeConn:
    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()
        self.committed = False

    def cursor(self, row_factory: Any = None) -> _FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


class _FakePool:
    def __init__(self) -> None:
        self.conn = _FakeConn()

    def connection(self):  # type: ignore[no-untyped-def]
        outer = self

        class _CM:
            def __enter__(self_inner):  # type: ignore[no-untyped-def]
                return outer.conn

            def __exit__(self_inner, *exc: Any) -> bool:  # type: ignore[no-untyped-def]
                return False

        return _CM()


def test_update_search_coverage_appends_entry_with_thesis_and_pillars() -> None:
    pool = _FakePool()
    repo = SourceRegisterRepository(pool)  # type: ignore[arg-type]

    source_id = uuid.uuid4()
    thesis_version_id = uuid.uuid4()
    pillar_a = uuid.uuid4()
    pillar_b = uuid.uuid4()

    repo.update_search_coverage(
        source_id=source_id,
        thesis_version_id=thesis_version_id,
        pillar_ids=[pillar_a, pillar_b],
    )

    assert pool.conn.committed is True
    assert len(pool.conn.cursor_obj.executed) == 1
    sql, params = pool.conn.cursor_obj.executed[0]
    assert "UPDATE source_register" in sql
    assert "search_coverage = search_coverage ||" in sql
    assert params[1] == source_id  # WHERE id = %s
    # entry is JSON-encoded; verify structure (ids stringified by the repo)
    entry_json = params[0]
    decoded = json.loads(entry_json)
    assert len(decoded) == 1
    assert decoded[0]["thesis_version_id"] == str(thesis_version_id)
    assert decoded[0]["pillar_ids"] == [str(pillar_a), str(pillar_b)]
