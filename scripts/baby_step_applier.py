from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class BabyStepApplierError(Exception):
    pass


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int


class BabyStepApplier:
    def __init__(self, plan_path: Path, commit: bool = False) -> None:
        self.plan_path = plan_path
        self.commit = commit
        self.plan = self._load_plan(plan_path)

    def run(self) -> int:
        self._print_header()
        self._confirm_branch()
        self._apply_files()
        self._run_command_blocks()

        for command in self.plan.get("validation_commands", []):
            result = self._run_shell(command, label="VALIDATE")
            if result.returncode != 0:
                self._print_failure(result)
                return result.returncode

        self._verify_expected_files()
        self._run_shell("git status --short", label="STATUS")
        self._run_shell("git diff --stat", label="DIFF")

        if self.commit:
            self._commit_if_changes_exist()
        else:
            print("\nPASS: plan applied and validation passed.")
            print("No commit was created because --commit was not supplied.")

        return 0

    def _load_plan(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise BabyStepApplierError(f"Plan file not found: {path}")

        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            raise BabyStepApplierError("Plan must be a YAML object.")

        required = ["step_id", "name", "branch", "objective", "commit_message"]
        missing = [key for key in required if key not in data]
        if missing:
            raise BabyStepApplierError(f"Plan missing required keys: {missing}")

        return data

    def _print_header(self) -> None:
        print("=" * 80)
        print("PFOS Baby Step Applier")
        print(f"Step: {self.plan['step_id']} — {self.plan['name']}")
        print(f"Branch: {self.plan['branch']}")
        print(f"Commit mode: {self.commit}")
        print("=" * 80)
        print(str(self.plan["objective"]).strip())
        print("=" * 80)

    def _confirm_branch(self) -> None:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        if result.returncode != 0:
            raise BabyStepApplierError(result.stderr.strip())

        current = result.stdout.strip()
        expected = str(self.plan["branch"])

        print(f"Current branch: {current}")

        if current != expected:
            raise BabyStepApplierError(f"Wrong branch. Expected {expected}, got {current}.")

    def _apply_files(self) -> None:
        files = self.plan.get("files", [])

        if files is None:
            return

        if not isinstance(files, list):
            raise BabyStepApplierError("files must be a list.")

        for file_spec in files:
            if not isinstance(file_spec, dict):
                raise BabyStepApplierError("Each file entry must be an object.")

            path_value = file_spec.get("path")
            content = file_spec.get("content")

            if not isinstance(path_value, str) or not path_value.strip():
                raise BabyStepApplierError("Each file entry requires a path.")

            if not isinstance(content, str):
                raise BabyStepApplierError(f"File {path_value} requires string content.")

            path = Path(path_value)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

            print(f"WROTE: {path}")

    def _run_command_blocks(self) -> None:
        commands = self.plan.get("commands", [])

        if commands is None:
            return

        if not isinstance(commands, list):
            raise BabyStepApplierError("commands must be a list.")

        for command_spec in commands:
            if isinstance(command_spec, str):
                name = command_spec
                run = command_spec
            elif isinstance(command_spec, dict):
                name = command_spec.get("name", "unnamed command")
                run = command_spec.get("run")
            else:
                raise BabyStepApplierError("Each command entry must be a string or object.")

            if not isinstance(name, str) or not name.strip():
                raise BabyStepApplierError("Command name must be a non-empty string.")

            if not isinstance(run, str) or not run.strip():
                raise BabyStepApplierError(f"Command {name} requires non-empty run content.")

            result = self._run_shell(run, label=f"COMMAND: {name}")
            if result.returncode != 0:
                raise BabyStepApplierError(
                    f"Command block failed: {name} with exit code {result.returncode}"
                )

    def _verify_expected_files(self) -> None:
        files_expected = self.plan.get("files_expected", [])

        if not files_expected:
            return

        if not isinstance(files_expected, list):
            raise BabyStepApplierError("files_expected must be a list.")

        missing = [file_path for file_path in files_expected if not Path(str(file_path)).exists()]
        if missing:
            raise BabyStepApplierError(f"Expected files missing: {missing}")

    def _run_shell(self, command: str, label: str) -> CommandResult:
        print("\n" + "-" * 80)
        print(label)
        print("-" * 80)
        print(command)
        print("-" * 80)

        result = subprocess.run(
            command,
            shell=True,
            text=True,
            check=False,
        )

        print(f"EXIT CODE: {result.returncode}")
        return CommandResult(command=command, returncode=result.returncode)

    def _print_failure(self, result: CommandResult) -> None:
        print("\nFAIL: validation stopped.")
        print(f"Failed command: {result.command}")
        print(f"Exit code: {result.returncode}")
        print("No commit was created.")

    def _commit_if_changes_exist(self) -> None:
        status = subprocess.run(
            ["git", "status", "--short"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        if status.returncode != 0:
            raise BabyStepApplierError(status.stderr.strip())

        if not status.stdout.strip():
            print("\nPASS: validation green, but no changes to commit.")
            return

        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", str(self.plan["commit_message"])], check=True)

        print("\nPASS: validation green and commit created.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a PFOS baby-step YAML plan.")
    parser.add_argument("plan", help="Path to baby-step YAML plan.")
    parser.add_argument("--commit", action="store_true", help="Commit if validation passes.")

    args = parser.parse_args()

    try:
        return BabyStepApplier(Path(args.plan), commit=args.commit).run()
    except BabyStepApplierError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
