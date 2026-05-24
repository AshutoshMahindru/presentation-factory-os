from __future__ import annotations

from system.approval_ledger_repository import ApprovalLedgerRepository


def test_approval_ledger_repository_exposes_snapshot_window_query() -> None:
    repository = ApprovalLedgerRepository()
    sql_project_id = "00000000-0000-0000-0000-000000000001"
    sql_phase = "review"

    # Build indirectly by monkeypatching _psql so this stays unit-level.
    captured: dict[str, str] = {}

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_psql(sql: str) -> FakeResult:
        captured["sql"] = sql
        return FakeResult()

    repository._psql = fake_psql  # type: ignore[method-assign]
    repository.list_approvals_for_phase(sql_project_id, sql_phase)

    assert "latest_phase_entry" in captured["sql"]
    assert "phase_transitions" in captured["sql"]
    assert "approval_ledger.created_at > latest_phase_entry.entered_at" in captured["sql"]
