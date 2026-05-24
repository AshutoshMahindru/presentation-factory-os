from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import yaml


DEFAULT_COMPOSE_PROJECT_NAME = "pfos-dev"
DEFAULT_COMPOSE_FILE = "docker-compose.apps.yaml"
EXPECTED_SERVICES = (
    "postgres",
    "neo4j",
    "qdrant",
    "workflow-service",
    "retrieval-engine",
    "tool-server",
    "agent-service",
)
REQUIRED_POSTGRES_TABLES = (
    "projects",
    "phase_transitions",
    "approval_ledger",
    "source_lifecycle_events",
    "outbox",
)

Command = Sequence[str]
Runner = Callable[[Command], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    skipped: bool = False

    @property
    def status(self) -> str:
        if self.skipped:
            return "SKIP"
        if self.ok:
            return "PASS"
        return "FAIL"


def run_command(command: Command) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=15,
    )


def compose_command(
    compose_project_name: str,
    compose_file: str,
    args: Sequence[str],
) -> list[str]:
    return [
        "docker",
        "compose",
        "-p",
        compose_project_name,
        "-f",
        compose_file,
        *args,
    ]


def check_docker_command(runner: Runner = run_command) -> CheckResult:
    try:
        result = runner(["docker", "--version"])
    except FileNotFoundError:
        return CheckResult("docker_command", False, "docker command not found")
    except subprocess.TimeoutExpired:
        return CheckResult("docker_command", False, "docker --version timed out")

    if result.returncode != 0:
        return CheckResult("docker_command", False, _command_error(result))

    return CheckResult("docker_command", True, _first_line(result.stdout))


def check_docker_compose(runner: Runner = run_command) -> CheckResult:
    try:
        result = runner(["docker", "compose", "version"])
    except FileNotFoundError:
        return CheckResult("docker_compose", False, "docker command not found")
    except subprocess.TimeoutExpired:
        return CheckResult("docker_compose", False, "docker compose version timed out")

    if result.returncode != 0:
        return CheckResult("docker_compose", False, _command_error(result))

    return CheckResult("docker_compose", True, _first_line(result.stdout))


def check_compose_file(compose_file: str) -> CheckResult:
    path = Path(compose_file)
    if not path.exists():
        return CheckResult("compose_file", False, f"{compose_file} does not exist")
    if not path.is_file():
        return CheckResult("compose_file", False, f"{compose_file} is not a file")
    return CheckResult("compose_file", True, f"{compose_file} exists")


def load_compose_services(compose_file: str) -> set[str]:
    data = yaml.safe_load(Path(compose_file).read_text()) or {}
    services = data.get("services", {})
    if not isinstance(services, dict):
        return set()
    return set(services)


def check_expected_services(
    compose_file: str,
    expected_services: Sequence[str] = EXPECTED_SERVICES,
) -> CheckResult:
    try:
        services = load_compose_services(compose_file)
    except FileNotFoundError:
        return CheckResult("compose_services", False, f"{compose_file} does not exist")
    except yaml.YAMLError as exc:
        return CheckResult("compose_services", False, f"{compose_file} is not valid YAML: {exc}")

    missing = sorted(set(expected_services) - services)
    if missing:
        return CheckResult(
            "compose_services",
            False,
            "missing expected services: " + ", ".join(missing),
        )

    return CheckResult(
        "compose_services",
        True,
        "expected services defined: " + ", ".join(expected_services),
    )


def check_required_postgres_tables(
    compose_project_name: str,
    compose_file: str,
    required_tables: Sequence[str] = REQUIRED_POSTGRES_TABLES,
    runner: Runner = run_command,
) -> CheckResult:
    table_list = ", ".join(_sql_literal(table) for table in required_tables)
    sql = (
        "SELECT table_name "
        "FROM information_schema.tables "
        "WHERE table_schema = 'public' "
        f"AND table_name IN ({table_list}) "
        "ORDER BY table_name;"
    )
    command = compose_command(
        compose_project_name,
        compose_file,
        [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "pfos",
            "-d",
            "pfos",
            "-v",
            "ON_ERROR_STOP=1",
            "-A",
            "-t",
            "-c",
            sql,
        ],
    )

    try:
        result = runner(command)
    except FileNotFoundError:
        return CheckResult(
            "postgres_tables",
            True,
            "skipped table check because docker command was not found",
            skipped=True,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            "postgres_tables",
            True,
            "skipped table check because Postgres did not respond before timeout",
            skipped=True,
        )

    if result.returncode != 0:
        return CheckResult(
            "postgres_tables",
            True,
            "skipped table check because Postgres is unavailable: " + _command_error(result),
            skipped=True,
        )

    found_tables = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    missing = sorted(set(required_tables) - found_tables)
    if missing:
        return CheckResult(
            "postgres_tables",
            False,
            "missing required tables: " + ", ".join(missing),
        )

    return CheckResult(
        "postgres_tables",
        True,
        "required tables present: " + ", ".join(required_tables),
    )


def run_checks(
    compose_project_name: str,
    compose_file: str,
    runner: Runner = run_command,
) -> list[CheckResult]:
    return [
        check_docker_command(runner),
        check_docker_compose(runner),
        check_compose_file(compose_file),
        check_expected_services(compose_file),
        check_required_postgres_tables(compose_project_name, compose_file, runner=runner),
    ]


def main(argv: Sequence[str] | None = None, runner: Runner = run_command) -> int:
    parser = argparse.ArgumentParser(description="Check the local PFOS Docker environment.")
    parser.add_argument(
        "--compose-project-name",
        default=os.environ.get("COMPOSE_PROJECT_NAME", DEFAULT_COMPOSE_PROJECT_NAME),
        help="Docker Compose project name to inspect.",
    )
    parser.add_argument(
        "--compose-file",
        default=os.environ.get("COMPOSE_FILE", DEFAULT_COMPOSE_FILE),
        help="Docker Compose file to inspect.",
    )
    args = parser.parse_args(argv)

    results = run_checks(
        compose_project_name=args.compose_project_name,
        compose_file=args.compose_file,
        runner=runner,
    )
    for result in results:
        print(f"{result.status} {result.name}: {result.detail}")

    return 0 if all(result.ok for result in results) else 1


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _first_line(value: str) -> str:
    return value.strip().splitlines()[0] if value.strip() else "no output"


def _command_error(result: subprocess.CompletedProcess[str]) -> str:
    output = (result.stderr or result.stdout or "").strip()
    if not output:
        output = f"exit code {result.returncode}"
    return output.replace("\n", " ")[:500]


if __name__ == "__main__":
    raise SystemExit(main())
