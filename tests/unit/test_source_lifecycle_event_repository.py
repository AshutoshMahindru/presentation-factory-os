from __future__ import annotations

import pytest

from system.source_lifecycle_event_repository import SourceLifecycleEventRepository


class FakeResult:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_source_lifecycle_event_repository_creates_pending_event() -> None:
    repository = SourceLifecycleEventRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult("event-1|project-1|source-1|retracted|pending\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    event = repository.create_event(
        project_id="project-1",
        source_id="source-1",
        event_type="retracted",
        event_payload={"reason": "source withdrawn"},
        hmac_validated=True,
    )

    assert event.event_id == "event-1"
    assert event.project_id == "project-1"
    assert event.source_id == "source-1"
    assert event.event_type == "retracted"
    assert event.processing_status == "pending"

    assert "INSERT INTO source_lifecycle_events" in captured["sql"]
    assert "'retracted'" in captured["sql"]
    assert "'pending'" in captured["sql"]
    assert '"reason": "source withdrawn"' in captured["sql"]
    assert "true" in captured["sql"]


def test_source_lifecycle_event_repository_rejects_unknown_event_type() -> None:
    repository = SourceLifecycleEventRepository()

    with pytest.raises(ValueError, match="Unsupported lifecycle event_type"):
        repository.create_event(
            project_id="project-1",
            source_id="source-1",
            event_type="not_real",
        )


def test_source_lifecycle_event_repository_escapes_sql_values() -> None:
    repository = SourceLifecycleEventRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult("event-1|project-with-'quote|source-with-'quote|updated|pending\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    repository.create_event(
        project_id="project-with-'quote",
        source_id="source-with-'quote",
        event_type="updated",
        event_payload={"title": "O'Reilly"},
    )

    assert "project-with-''quote" in captured["sql"]
    assert "source-with-''quote" in captured["sql"]
    assert "O''Reilly" in captured["sql"]
