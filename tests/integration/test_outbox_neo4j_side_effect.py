import os
import subprocess
from uuid import UUID

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


def cypher(query: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "neo4j",
            "cypher-shell",
            "-u",
            "neo4j",
            "-p",
            "pfos_neo4j_password",
            query,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def extract_uuid(stdout: str) -> str:
    for line in stdout.splitlines():
        candidate = line.strip()
        try:
            UUID(candidate)
            return candidate
        except ValueError:
            continue
    raise AssertionError(f"No UUID found in psql output: {stdout}")


def test_outbox_worker_writes_project_node_to_neo4j():
    setup = """
    WITH project AS (
      INSERT INTO projects (name, audience, audience_profile, current_phase)
      VALUES ('Outbox Neo4j Project', 'Investment committee', '{}'::jsonb, 'intake')
      RETURNING id
    )
    INSERT INTO outbox (project_id, target_store, operation_type, payload)
    SELECT
      id,
      'neo4j',
      'phase_transition_side_effect',
      '{"project_name":"Outbox Neo4j Project","to_phase":"strategy"}'::jsonb
    FROM project
    RETURNING id, project_id;
    """

    setup_result = psql(setup)
    assert setup_result.returncode == 0, setup_result.stderr

    # First UUID is outbox id; second UUID is project id.
    uuids = []
    for line in setup_result.stdout.splitlines():
        for part in line.split("|"):
            candidate = part.strip()
            try:
                UUID(candidate)
                uuids.append(candidate)
            except ValueError:
                pass

    assert len(uuids) >= 2, setup_result.stdout
    project_id = uuids[1]

    worker_result = subprocess.run(
        ["python", "-m", "jobs.outbox_worker"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert worker_result.returncode == 0, worker_result.stderr

    check = cypher(
        f"""
        MATCH (p:Project {{id: '{project_id}'}})
        RETURN p.id AS id, p.name AS name, p.current_phase AS current_phase;
        """
    )

    assert check.returncode == 0, check.stderr
    assert project_id in check.stdout
    assert "Outbox Neo4j Project" in check.stdout
    assert "strategy" in check.stdout


def test_outbox_worker_is_idempotent_for_project_node_merge():
    setup = """
    WITH project AS (
      INSERT INTO projects (name, audience, audience_profile, current_phase)
      VALUES ('Outbox Idempotent Project', 'Investment committee', '{}'::jsonb, 'intake')
      RETURNING id
    )
    INSERT INTO outbox (project_id, target_store, operation_type, payload)
    SELECT
      id,
      'neo4j',
      'phase_transition_side_effect',
      '{"project_name":"Outbox Idempotent Project","to_phase":"strategy"}'::jsonb
    FROM project
    RETURNING project_id;
    """

    setup_result = psql(setup)
    assert setup_result.returncode == 0, setup_result.stderr
    project_id = extract_uuid(setup_result.stdout)

    first = subprocess.run(
        ["python", "-m", "jobs.outbox_worker"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    second = subprocess.run(
        ["python", "-m", "jobs.outbox_worker"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    check = cypher(
        f"""
        MATCH (p:Project {{id: '{project_id}'}})
        RETURN count(p) AS project_count;
        """
    )

    assert check.returncode == 0, check.stderr
    assert "1" in check.stdout
