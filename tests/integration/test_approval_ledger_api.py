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


def create_project():
    response = client.post(
        "/projects",
        json={
            "name": "Approval Ledger Project",
            "audience": "Investment committee",
            "audience_profile": valid_audience_profile(),
        },
    )
    assert response.status_code == 200
    return response.json()["project_id"]


def test_submit_intake_approval_records_ledger_row_and_meets_quorum():
    project_id = create_project()

    response = client.post(
        f"/projects/{project_id}/approvals",
        json={
            "phase": "intake",
            "actor_email": "analyst@example.com",
            "role": "analyst",
            "decision": "approved",
            "rubric_score_snapshot": {"overall_score": 3.8},
            "notes": "Intake is complete.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_recorded"] is True
    assert body["quorum_met"] is True
    assert body["approved_count"] == 1

    check = psql(
        f"""
        SELECT phase, actor_email, role, decision
        FROM approval_ledger
        WHERE project_id = '{project_id}';
        """
    )

    assert check.returncode == 0, check.stderr
    assert "intake|analyst@example.com|analyst|approved" in check.stdout


def test_strategy_approval_requires_partner_role():
    project_id = create_project()

    response = client.post(
        f"/projects/{project_id}/approvals",
        json={
            "phase": "strategy",
            "actor_email": "senior@example.com",
            "role": "senior_partner",
            "decision": "approved",
            "rubric_score_snapshot": {"overall_score": 4.0},
            "notes": "Looks good.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["quorum_met"] is False
    assert body["missing_roles"] == {"partner": 1}


def test_invalid_approval_role_rejected_by_sql_or_quorum():
    project_id = create_project()

    response = client.post(
        f"/projects/{project_id}/approvals",
        json={
            "phase": "strategy",
            "actor_email": "bad@example.com",
            "role": "not_a_role",
            "decision": "approved",
            "rubric_score_snapshot": {},
        },
    )

    assert response.status_code == 422
