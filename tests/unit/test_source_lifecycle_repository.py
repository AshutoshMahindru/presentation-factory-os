from __future__ import annotations

from system.source_lifecycle_repository import (
    RetractionCascadeStatus,
    SourceLifecycleRepository,
)


class FakeResult:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_source_lifecycle_repository_reports_clean_project() -> None:
    repository = SourceLifecycleRepository()

    def fake_psql(sql: str) -> FakeResult:
        return FakeResult("0|0|0|\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    status = repository.get_project_retraction_cascade_status("project-1")

    assert status == RetractionCascadeStatus(
        project_id="project-1",
        blocked=False,
        pending_count=0,
        processing_count=0,
        failed_count=0,
        oldest_open_age_seconds=None,
    )


def test_source_lifecycle_repository_reports_open_retraction_events_as_blocking() -> None:
    repository = SourceLifecycleRepository()

    def fake_psql(sql: str) -> FakeResult:
        return FakeResult("2|1|1|77\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    status = repository.get_project_retraction_cascade_status("project-2")

    assert status.blocked is True
    assert status.pending_count == 2
    assert status.processing_count == 1
    assert status.failed_count == 1
    assert status.oldest_open_age_seconds == 77


def test_source_lifecycle_repository_sql_is_project_scoped_and_retraction_only() -> None:
    repository = SourceLifecycleRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult("0|0|0|\n")

    repository._psql = fake_psql  # type: ignore[method-assign]
    repository.get_project_retraction_cascade_status("project-with-'quote")

    assert "FROM source_lifecycle_events" in captured["sql"]
    assert "project_id = 'project-with-''quote'" in captured["sql"]
    assert "event_type = 'retracted'" in captured["sql"]
    assert "processing_status IN ('pending', 'processing', 'failed')" in captured["sql"]
