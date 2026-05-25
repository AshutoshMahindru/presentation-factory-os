from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from scripts import generate_phase_enums
from system.generated_phase_enums import PHASES, PHASE_VALUES, Phase


REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_MACHINE_SPEC = REPO_ROOT / "docs" / "08_StateMachine_Spec.yaml"


def yaml_phases() -> tuple[str, ...]:
    spec = yaml.safe_load(STATE_MACHINE_SPEC.read_text())
    return tuple(spec["phases"])


def test_generated_python_enum_matches_state_machine_spec() -> None:
    phases = yaml_phases()

    assert PHASE_VALUES == phases
    assert tuple(phase.value for phase in Phase) == phases
    assert tuple(phase.value for phase in PHASES) == phases


def test_generated_typescript_matches_state_machine_spec() -> None:
    phases = yaml_phases()
    expected = generate_phase_enums.render_typescript(phases)

    assert generate_phase_enums.TYPESCRIPT_OUTPUT.read_text() == expected


def test_generated_python_file_matches_state_machine_spec() -> None:
    phases = yaml_phases()
    expected = generate_phase_enums.render_python(phases)

    assert generate_phase_enums.PYTHON_OUTPUT.read_text() == expected


def test_check_mode_passes_for_checked_in_outputs() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate_phase_enums.py", "--check"],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_check_generated_detects_stale_output(tmp_path: Path) -> None:
    stale_file = tmp_path / "phaseTypes.ts"
    stale_file.write_text("stale\n")

    try:
        generate_phase_enums.check_generated({stale_file: "fresh\n"})
    except SystemExit as error:
        assert "Generated phase enum files are stale" in str(error)
    else:
        raise AssertionError("Expected stale generated output to fail check mode.")
