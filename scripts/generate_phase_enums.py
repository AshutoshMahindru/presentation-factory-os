from __future__ import annotations

import argparse
import re
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_MACHINE_SPEC = REPO_ROOT / "docs" / "08_StateMachine_Spec.yaml"
PYTHON_OUTPUT = REPO_ROOT / "system" / "generated_phase_enums.py"
TYPESCRIPT_OUTPUT = REPO_ROOT / "ui" / "lib" / "phaseTypes.ts"

HEADER = (
    "Generated from docs/08_StateMachine_Spec.yaml by "
    "scripts/generate_phase_enums.py. Do not edit by hand."
)


class PhaseEnumCodegenError(Exception):
    """Raised when phase enum generation cannot proceed."""


def load_phases(spec_path: Path = STATE_MACHINE_SPEC) -> tuple[str, ...]:
    spec = yaml.safe_load(spec_path.read_text())
    if not isinstance(spec, dict):
        raise PhaseEnumCodegenError(f"State machine spec must be a YAML object: {spec_path}")

    phases = spec.get("phases")
    if not isinstance(phases, list) or not phases:
        raise PhaseEnumCodegenError("State machine spec requires a non-empty phases list.")

    normalized: list[str] = []
    seen: set[str] = set()
    for phase in phases:
        if not isinstance(phase, str) or not phase:
            raise PhaseEnumCodegenError("Every phase must be a non-empty string.")
        if phase in seen:
            raise PhaseEnumCodegenError(f"Duplicate phase in state machine spec: {phase}")
        seen.add(phase)
        normalized.append(phase)

    return tuple(normalized)


def enum_member_name(phase: str) -> str:
    name = re.sub(r"[^0-9A-Za-z]+", "_", phase).strip("_").upper()
    if not name:
        raise PhaseEnumCodegenError(f"Cannot derive enum member name from phase: {phase!r}")
    if name[0].isdigit():
        name = f"PHASE_{name}"
    if name in Enum.__members__:
        name = f"PHASE_{name}"
    return name


def render_python(phases: tuple[str, ...]) -> str:
    member_names: set[str] = set()
    members: list[str] = []
    for phase in phases:
        member_name = enum_member_name(phase)
        if member_name in member_names:
            raise PhaseEnumCodegenError(
                f"Phase names generate duplicate Python enum member {member_name}."
            )
        member_names.add(member_name)
        members.append(f'    {member_name} = "{phase}"')

    phase_values = ",\n    ".join(f'Phase.{enum_member_name(phase)}' for phase in phases)
    if len(phases) == 1:
        phase_values = f"{phase_values},"

    return "\n".join(
        [
            '"""',
            HEADER,
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "from enum import Enum",
            "",
            "",
            "class Phase(str, Enum):",
            *members,
            "",
            "",
            "PHASES: tuple[Phase, ...] = (",
            f"    {phase_values}",
            ")",
            "",
            "",
            "PHASE_VALUES: tuple[str, ...] = tuple(phase.value for phase in PHASES)",
            "",
        ]
    )


def render_typescript(phases: tuple[str, ...]) -> str:
    values = ",\n  ".join(f'"{phase}"' for phase in phases)
    return "\n".join(
        [
            f"// {HEADER}",
            "",
            "export const PHASES = [",
            f"  {values},",
            "] as const;",
            "",
            "export type Phase = (typeof PHASES)[number];",
            "",
            "export function isPhase(value: string): value is Phase {",
            "  return (PHASES as readonly string[]).includes(value);",
            "}",
            "",
        ]
    )


def generated_files(phases: tuple[str, ...]) -> dict[Path, str]:
    return {
        PYTHON_OUTPUT: render_python(phases),
        TYPESCRIPT_OUTPUT: render_typescript(phases),
    }


def write_generated(files: dict[Path, str]) -> None:
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"WROTE {path.relative_to(REPO_ROOT)}")


def check_generated(files: dict[Path, str]) -> None:
    stale: list[Path] = []
    for path, expected in files.items():
        if not path.exists() or path.read_text() != expected:
            stale.append(path)

    if stale:
        formatted = ", ".join(display_path(path) for path in stale)
        raise SystemExit(
            f"Generated phase enum files are stale: {formatted}. "
            "Run `make codegen-phase-enums`."
        )

    for path in files:
        print(f"PASS {display_path(path)}")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate phase enums from docs/08_StateMachine_Spec.yaml."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated files do not match the state machine spec.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    phases = load_phases()
    files = generated_files(phases)

    if args.check:
        check_generated(files)
    else:
        write_generated(files)


if __name__ == "__main__":
    main()
