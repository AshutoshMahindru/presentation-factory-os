from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.baby_step_applier import BabyStepApplier, BabyStepApplierError


def write_plan(tmp_path: Path, extra: dict | None = None) -> Path:
    plan = {
        "step_id": 999,
        "name": "test_step",
        "branch": "test-branch",
        "objective": "Test baby-step applier.",
        "commit_message": "Test commit",
        "validation_commands": [],
        "files": [
            {
                "path": str(tmp_path / "generated" / "hello.txt"),
                "content": "hello world\n",
            }
        ],
        "files_expected": [
            str(tmp_path / "generated" / "hello.txt"),
        ],
    }

    if extra:
        plan.update(extra)

    plan_path = tmp_path / "plan.yaml"
    plan_path.write_text(yaml.safe_dump(plan, sort_keys=False))
    return plan_path


def test_load_plan_requires_yaml_object(tmp_path: Path) -> None:
    plan_path = tmp_path / "bad.yaml"
    plan_path.write_text("- not\n- object\n")

    with pytest.raises(BabyStepApplierError, match="YAML object"):
        BabyStepApplier(plan_path)


def test_missing_required_key_raises_error(tmp_path: Path) -> None:
    plan_path = tmp_path / "bad.yaml"
    plan_path.write_text(yaml.safe_dump({"step_id": 1}))

    with pytest.raises(BabyStepApplierError, match="missing required keys"):
        BabyStepApplier(plan_path)


def test_apply_files_writes_embedded_file_content(tmp_path: Path) -> None:
    plan_path = write_plan(tmp_path)
    applier = BabyStepApplier(plan_path)

    applier._apply_files()

    written = tmp_path / "generated" / "hello.txt"
    assert written.exists()
    assert written.read_text() == "hello world\n"


def test_verify_expected_files_detects_missing_file(tmp_path: Path) -> None:
    plan_path = write_plan(tmp_path)
    applier = BabyStepApplier(plan_path)

    with pytest.raises(BabyStepApplierError, match="Expected files missing"):
        applier._verify_expected_files()


def test_verify_expected_files_passes_after_file_apply(tmp_path: Path) -> None:
    plan_path = write_plan(tmp_path)
    applier = BabyStepApplier(plan_path)

    applier._apply_files()
    applier._verify_expected_files()
