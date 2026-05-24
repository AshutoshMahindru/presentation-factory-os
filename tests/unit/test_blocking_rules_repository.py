from __future__ import annotations

from system.blocking_rules_repository import BlockingRulesRepository, BlockingRulesStatus


class FakeResult:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_blocking_rules_repository_returns_clean_when_table_missing() -> None:
    repository = BlockingRulesRepository()
    calls: list[str] = []

    def fake_psql(sql: str) -> FakeResult:
        calls.append(sql)
        return FakeResult("f\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    status = repository.get_project_blocking_rules_status("project-1")

    assert status == BlockingRulesStatus(
        project_id="project-1",
        blocked=False,
        blocking_count=0,
        warning_count=0,
        info_count=0,
    )
    assert len(calls) == 1


def test_blocking_rules_repository_reports_open_blocking_rules() -> None:
    repository = BlockingRulesRepository()
    calls: list[str] = []

    def fake_psql(sql: str) -> FakeResult:
        calls.append(sql)
        if len(calls) == 1:
            return FakeResult("t\n")
        return FakeResult("2|3|4\n")

    repository._psql = fake_psql  # type: ignore[method-assign]

    status = repository.get_project_blocking_rules_status("project-2")

    assert status.blocked is True
    assert status.blocking_count == 2
    assert status.warning_count == 3
    assert status.info_count == 4
    assert len(calls) == 2


def test_blocking_rules_repository_sql_is_project_scoped() -> None:
    repository = BlockingRulesRepository()
    calls: list[str] = []

    def fake_psql(sql: str) -> FakeResult:
        calls.append(sql)
        if len(calls) == 1:
            return FakeResult("t\n")
        return FakeResult("0|0|0\n")

    repository._psql = fake_psql  # type: ignore[method-assign]
    repository.get_project_blocking_rules_status("project-with-'quote")

    assert "FROM blocking_rules" in calls[1]
    assert "project_id = 'project-with-''quote'" in calls[1]
    assert "severity = 'blocking'" in calls[1]
    assert "resolved = FALSE" in calls[1]
