from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

from scripts import check_docker_env


def completed(
    command: Sequence[str],
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        list(command),
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


class FakeRunner:
    def __init__(self, responses: Sequence[subprocess.CompletedProcess[str]]) -> None:
        self.responses = list(responses)
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(command))
        if not self.responses:
            raise AssertionError(f"unexpected command: {command}")
        return self.responses.pop(0)


def write_compose_file(tmp_path: Path, services: Sequence[str]) -> Path:
    service_yaml = "\n".join(f"  {service}:\n    image: test" for service in services)
    compose_file = tmp_path / "docker-compose.apps.yaml"
    compose_file.write_text(f"services:\n{service_yaml}\n")
    return compose_file


def test_compose_command_uses_canonical_project_and_file() -> None:
    command = check_docker_env.compose_command(
        "pfos-dev",
        "docker-compose.apps.yaml",
        ["ps"],
    )

    assert command == [
        "docker",
        "compose",
        "-p",
        "pfos-dev",
        "-f",
        "docker-compose.apps.yaml",
        "ps",
    ]


def test_check_expected_services_passes_when_all_required_services_exist(tmp_path: Path) -> None:
    compose_file = write_compose_file(tmp_path, check_docker_env.EXPECTED_SERVICES)

    result = check_docker_env.check_expected_services(str(compose_file))

    assert result.ok is True
    assert result.status == "PASS"


def test_check_expected_services_fails_when_required_service_is_missing(tmp_path: Path) -> None:
    services = [service for service in check_docker_env.EXPECTED_SERVICES if service != "agent-service"]
    compose_file = write_compose_file(tmp_path, services)

    result = check_docker_env.check_expected_services(str(compose_file))

    assert result.ok is False
    assert result.status == "FAIL"
    assert "agent-service" in result.detail


def test_required_postgres_tables_check_skips_when_database_is_unavailable() -> None:
    runner = FakeRunner(
        [
            completed(
                ["docker"],
                returncode=1,
                stderr="service postgres is not running",
            )
        ]
    )

    result = check_docker_env.check_required_postgres_tables(
        "pfos-dev",
        "docker-compose.apps.yaml",
        runner=runner,
    )

    assert result.ok is True
    assert result.skipped is True
    assert result.status == "SKIP"
    assert "Postgres is unavailable" in result.detail


def test_required_postgres_tables_check_fails_when_reachable_database_lacks_tables() -> None:
    found_tables = "\n".join(
        table
        for table in check_docker_env.REQUIRED_POSTGRES_TABLES
        if table != "outbox"
    )
    runner = FakeRunner([completed(["docker"], stdout=f"{found_tables}\n")])

    result = check_docker_env.check_required_postgres_tables(
        "pfos-dev",
        "docker-compose.apps.yaml",
        runner=runner,
    )

    assert result.ok is False
    assert result.status == "FAIL"
    assert "outbox" in result.detail


def test_main_returns_nonzero_when_compose_file_is_missing(tmp_path: Path, capsys) -> None:
    missing_compose_file = tmp_path / "missing-compose.yaml"
    runner = FakeRunner(
        [
            completed(["docker"], stdout="Docker version 1\n"),
            completed(["docker"], stdout="Docker Compose version 2\n"),
            completed(["docker"], returncode=1, stderr="no compose file"),
        ]
    )

    exit_code = check_docker_env.main(
        [
            "--compose-project-name",
            "pfos-dev",
            "--compose-file",
            str(missing_compose_file),
        ],
        runner=runner,
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL compose_file" in output
