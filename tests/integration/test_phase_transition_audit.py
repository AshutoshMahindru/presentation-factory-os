import subprocess

from fastapi.testclient import TestClient

from api.workflow import app


COMPOSE = ["docker", "compose", "-f", "docker-compose.apps.yaml"]
client = TestClient(app)


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


def valid_audience_profile():
    return {
        "decision_maker_type": "ic_partner",
        "risk_tolerance": "medium",
        "familiarity_with_topic": "informed",
        "known_objections": ["pricing", "timing", "team_risk"],
        "stakeholder_map": [
            {
                "role": "economic_buyer",
                "concern": "roi",
            }
        ],
    }


def test_successful_phase_transition_writes_audit_row():
    create = client.post(
        "/projects",
        json={
            "name": "Audit Project",
            "audience": "Investment committee",
            "audience_profile": valid_audience_profile(),
        },
    )
    assert create.status_code == 200
    project_id = create.json()["project_id"]

    transition = client.post(
        f"/projects/{project_id}/phase-transitions",
        json={
            "from_phase": "created",
            "to_phase": "intake",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Begin intake.",
            "guard_context": {"guards": {}},
        },
    )

    assert transition.status_code == 200

    check = psql(
        f"""
        SELECT from_phase, to_phase, transition_kind, state_machine_version, actor_email, reason
        FROM phase_transitions
        WHERE project_id = '{project_id}'
        ORDER BY created_at DESC
        LIMIT 1;
        """
    )

    assert check.returncode == 0, check.stderr
    assert "created|intake|forward|3.2.4|analyst@example.com|Begin intake." in check.stdout


def test_failed_phase_transition_does_not_write_audit_row():
    create = client.post(
        "/projects",
        json={
            "name": "Failed Audit Project",
            "audience": "Investment committee",
            "audience_profile": valid_audience_profile(),
        },
    )
    assert create.status_code == 200
    project_id = create.json()["project_id"]

    transition = client.post(
        f"/projects/{project_id}/phase-transitions",
        json={
            "from_phase": "created",
            "to_phase": "strategy",
            "transition_kind": "forward",
            "requested_by": "analyst@example.com",
            "reason": "Invalid jump.",
            "guard_context": {"guards": {}},
        },
    )

    assert transition.status_code == 422

    check = psql(
        f"""
        SELECT count(*)
        FROM phase_transitions
        WHERE project_id = '{project_id}';
        """
    )

    assert check.returncode == 0, check.stderr
    assert check.stdout.strip() == "0"
