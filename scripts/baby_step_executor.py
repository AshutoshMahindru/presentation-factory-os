from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int


class BabyStepExecutorError(Exception):
    pass


class BabyStepExecutor:
    def __init__(self, plan_path: Path, commit: bool = False) -> None:
        self.plan_path = plan_path
        self.commit = commit
        self.plan = self._load_plan(plan_path)

    def run(self) -> int:
        self._print_header()

        self._require_clean_or_explain()
        self._confirm_branch()

        results: list[CommandResult] = []

        for command in self.plan.get("validation_commands", []):
            results.append(self._run_command(command))
            if results[-1].returncode != 0:
                self._print_failure(results[-1])
                return results[-1].returncode

        self._run_command("git status --short")
        self._run_command("git diff --stat")

        if self.commit:
            self._commit_if_green()
        else:
            print("\nPASS: validation commands completed.")
            print("No commit was created because --commit was not supplied.")
            print("Review the diff, then rerun with --commit if appropriate.")

        return 0

    def _load_plan(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise BabyStepExecutorError(f"Plan file not found: {path}")

        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            raise BabyStepExecutorError(f"Plan file must contain a YAML object: {path}")

        required = ["step_id", "name", "branch", "objective", "commit_message", "validation_commands"]
        missing = [key for key in required if key not in data]
        if missing:
            raise BabyStepExecutorError(f"Plan file missing required keys: {missing}")

        if not isinstance(data["validation_commands"], list) or not data["validation_commands"]:
            raise BabyStepExecutorError("validation_commands must be a non-empty list.")

        return data

    def _print_header(self) -> None:
        print("=" * 80)
        print(f"PFOS Baby Step Executor")
        print(f"Step: {self.plan['step_id']} — {self.plan['name']}")
        print(f"Branch: {self.plan['branch']}")
        print(f"Commit mode: {self.commit}")
        print("=" * 80)
        print(self.plan["objective"].strip())
        print("=" * 80)

    def _require_clean_or_explain(self) -> None:
        result = subprocess.run(
            ["git", "status", "--short"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        if result.returncode != 0:
            raise BabyStepExecutorError(result.stderr)

        if result.stdout.strip():
            print("Working tree has changes. This is allowed for validation.")
            print("Current changed files:")
            print(result.stdout)
        else:
            print("Working tree clean before execution.")

    def _confirm_branch(self) -> None:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        if result.returncode != 0:
            raise BabyStepExecutorError(result.stderr)

        current_branch = result.stdout.strip()
        expected_branch = str(self.plan["branch"])

        print(f"Current branch: {current_branch}")

        if current_branch != expected_branch:
            raise BabyStepExecutorError(
                f"Wrong branch. Expected {expected_branch}, got {current_branch}."
            )

    def _run_command(self, command: str) -> CommandResult:
        print("\n" + "-" * 80)
        print(f"RUN: {command}")
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

    def _commit_if_green(self) -> None:
        status = subprocess.run(
            ["git", "status", "--short"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        if status.returncode != 0:
            raise BabyStepExecutorError(status.stderr)

        if not status.stdout.strip():
            print("\nPASS: validation green, but no changes to commit.")
            return

        files_expected = self.plan.get("files_expected", [])
        if files_expected:
            for file_path in files_expected:
                if not Path(file_path).exists():
                    raise BabyStepExecutorError(f"Expected file missing: {file_path}")

        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", str(self.plan["commit_message"])], check=True)

        print("\nPASS: validation green and commit created.")


def main() -> int:
    parser = argparse.ArgumentParser(description="PFOS conservative baby-step executor.")
    parser.add_argument("plan", help="Path to baby-step YAML plan.")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Create a git commit if validation passes and changes exist.",
    )

    args = parser.parse_args()

    try:
        return BabyStepExecutor(plan_path=Path(args.plan), commit=args.commit).run()
    except BabyStepExecutorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
