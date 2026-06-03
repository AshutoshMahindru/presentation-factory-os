from pathlib import Path

import pytest

from system.design_override_repository import DesignOverrideRepository


ROOT = Path(__file__).resolve().parents[2]


def test_design_override_repository_records_reapproval_audit():
    repo = DesignOverrideRepository()

    record = repo.record_override(
        project_id="project_001",
        slide_id="slide_001",
        field_path="content.headline",
        old_value="Old",
        new_value="New",
        actor="operator@example.com",
        reason="Tighten executive wording",
    )

    assert record.triggers_reapproval is True
    assert record.override_id
    assert repo.list_project_overrides("project_001") == [record]


def test_design_override_repository_requires_reason_and_change():
    repo = DesignOverrideRepository()

    with pytest.raises(ValueError, match="reason"):
        repo.record_override(
            project_id="project_001",
            slide_id="slide_001",
            field_path="content.headline",
            old_value="Old",
            new_value="New",
            actor="operator@example.com",
            reason="",
        )

    with pytest.raises(ValueError, match="change"):
        repo.record_override(
            project_id="project_001",
            slide_id="slide_001",
            field_path="content.headline",
            old_value="Same",
            new_value="Same",
            actor="operator@example.com",
            reason="No-op check",
        )


def test_design_override_panel_exports_audit_ui_contract():
    source = (ROOT / "ui" / "components" / "DesignOverridePanel.tsx").read_text()

    assert "export function DesignOverridePanel" in source
    assert "triggers_reapproval" in source
    assert "Re-approval required" in source
