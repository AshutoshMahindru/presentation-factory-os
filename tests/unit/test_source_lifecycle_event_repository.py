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


def test_source_lifecycle_event_repository_rejects_unknown_processing_status() -> None:
    repository = SourceLifecycleEventRepository()

    with pytest.raises(ValueError, match="Unsupported processing_status"):
        repository.create_event(
            project_id="project-1",
            source_id="source-1",
            event_type="retracted",
            processing_status="not_real",
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


def test_source_lifecycle_event_repository_updates_processing_status() -> None:
    repository = SourceLifecycleEventRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult("event-1|project-1|source-1|retracted|processed\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    event = repository.update_processing_status(
        event_id="event-1",
        processing_status="processed",
    )

    assert event.event_id == "event-1"
    assert event.processing_status == "processed"
    assert "UPDATE source_lifecycle_events" in captured["sql"]
    assert "processing_status = 'processed'" in captured["sql"]
    assert "processed_at = now()" in captured["sql"]


def test_source_lifecycle_event_repository_failed_status_increments_error_count() -> None:
    repository = SourceLifecycleEventRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult("event-1|project-1|source-1|retracted|failed\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    event = repository.update_processing_status(
        event_id="event-1",
        processing_status="failed",
        last_error="neo4j unavailable",
    )

    assert event.processing_status == "failed"
    assert "error_count = error_count + 1" in captured["sql"]
    assert "last_error = 'neo4j unavailable'" in captured["sql"]


def test_source_lifecycle_event_repository_update_404_when_no_row_returned() -> None:
    repository = SourceLifecycleEventRepository()

    def fake_psql(sql: str) -> FakeResult:
        return FakeResult("")

    repository._psql = fake_psql  # type: ignore[method-assign]

    with pytest.raises(LookupError, match="Source lifecycle event not found"):
        repository.update_processing_status(
            event_id="missing-event",
            processing_status="processed",
        )


def test_source_lifecycle_event_repository_rejects_invalid_status_update() -> None:
    repository = SourceLifecycleEventRepository()

    with pytest.raises(ValueError, match="Unsupported processing_status"):
        repository.update_processing_status(
            event_id="event-1",
            processing_status="not_real",
        )


def test_source_lifecycle_event_repository_get_event() -> None:
    repository = SourceLifecycleEventRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult("event-1|project-1|source-1|retracted|processed\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    event = repository.get_event("event-1")

    assert event.event_id == "event-1"
    assert event.processing_status == "processed"
    assert "WHERE id = 'event-1'" in captured["sql"]


def test_source_lifecycle_event_repository_get_event_raises_when_missing() -> None:
    repository = SourceLifecycleEventRepository()

    def fake_psql(sql: str) -> FakeResult:
        return FakeResult("")

    repository._psql = fake_psql  # type: ignore[method-assign]

    with pytest.raises(LookupError, match="Source lifecycle event not found"):
        repository.get_event("missing-event")


def test_source_lifecycle_event_repository_claims_pending_retractions_with_skip_locked() -> None:
    repository = SourceLifecycleEventRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult("event-1|project-1|source-1|retracted|processing\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    events = repository.claim_pending_retraction_events(limit=10)

    assert len(events) == 1
    assert events[0].event_id == "event-1"
    assert events[0].processing_status == "processing"
    assert "FOR UPDATE SKIP LOCKED" in captured["sql"]
    assert "processing_status = 'pending'" in captured["sql"]
    assert "processing_status = 'processing'" in captured["sql"]
    assert "LIMIT 10" in captured["sql"]


def test_source_lifecycle_event_repository_claim_rejects_invalid_limit() -> None:
    repository = SourceLifecycleEventRepository()

    with pytest.raises(ValueError, match="limit must be between 1 and 50"):
        repository.claim_pending_retraction_events(limit=99)
