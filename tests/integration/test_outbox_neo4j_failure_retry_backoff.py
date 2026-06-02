import os
import subprocess

import pytest


COMPOSE = ["docker", "compose", "-f", "docker-compose.apps.yaml"]
pytestmark = pytest.mark.skipif(
    os.environ.get("PFOS_RUN_LIVE_TESTS") != "1",
    reason="Live Docker/Postgres/Neo4j smoke test; set PFOS_RUN_LIVE_TESTS=1",
)


def psql(sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            *COMPOSE,
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
            "-F",
            "|",
            "-c",
            sql,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def extract_uuid(stdout: str) -> str:
    for line in stdout.splitlines():
        candidate = line.strip()
        if len(candidate) == 36 and candidate.count("-") == 4:
            return candidate
    raise AssertionError(f"No UUID found in psql output: {stdout}")


def test_outbox_failure_increments_error_count_and_records_error():
    setup = """
    WITH project AS (
      INSERT INTO projects (name, audience, audience_profile)
      VALUES ('Outbox Retry Project', 'Investment committee', '{}'::jsonb)
      RETURNING id
    )
    INSERT INTO outbox (project_id, target_store, operation_type, payload)
    SELECT id, 'neo4j', 'phase_transition_side_effect', '{"force_error":true}'::jsonb
    FROM project
    RETURNING id;
    """

    setup_result = psql(setup)
    assert setup_result.returncode == 0, setup_result.stderr
    outbox_id = extract_uuid(setup_result.stdout)

    worker_result = subprocess.run(
        ["python", "-m", "jobs.outbox_worker"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )

    assert worker_result.returncode == 0, worker_result.stderr

    check = psql(
        f"""
        SELECT processed, error_count, last_error
        FROM outbox
        WHERE id = '{outbox_id}';
        """
    )
    assert check.returncode == 0, check.stderr
    assert "f|1|Forced outbox operation failure" in check.stdout
