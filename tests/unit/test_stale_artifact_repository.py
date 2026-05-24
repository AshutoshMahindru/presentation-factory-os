from __future__ import annotations

from system.stale_artifact_repository import StaleArtifactRepository, StaleArtifactStatus


class FakeResult:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_stale_artifact_repository_reports_clean_project() -> None:
    repository = StaleArtifactRepository()

    def fake_psql(sql: str) -> FakeResult:
        return FakeResult("0|0\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    status = repository.get_project_stale_artifact_status("project-1")

    assert status == StaleArtifactStatus(
        project_id="project-1",
        blocked=False,
        financial_cells_count=0,
        design_tokens_count=0,
        total_count=0,
    )


def test_stale_artifact_repository_reports_stale_artifacts_as_blocking() -> None:
    repository = StaleArtifactRepository()

    def fake_psql(sql: str) -> FakeResult:
        return FakeResult("2|3\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    status = repository.get_project_stale_artifact_status("project-2")

    assert status.blocked is True
    assert status.financial_cells_count == 2
    assert status.design_tokens_count == 3
    assert status.total_count == 5


def test_stale_artifact_repository_sql_is_project_scoped_and_stale_only() -> None:
    repository = StaleArtifactRepository()
    captured: dict[str, str] = {}

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult("0|0\n")

    repository._psql = fake_psql  # type: ignore[method-assign]
    repository.get_project_stale_artifact_status("project-with-'quote")

    assert "FROM financial_cells" in captured["sql"]
    assert "FROM design_tokens" in captured["sql"]
    assert "project_id = 'project-with-''quote'" in captured["sql"]
    assert "artifact_status = 'stale_due_to_retreat'" in captured["sql"]
