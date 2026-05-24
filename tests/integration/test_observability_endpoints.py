import subprocess
from uuid import UUID

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


def create_project(name: str = "Observability Endpoint Project") -> str:
    response = client.post(
        "/projects",
        json={
            "name": name,
            "audience": "Investment committee",
            "audience_profile": valid_audience_profile(),
        },
    )
    assert response.status_code == 200
    return response.json()["project_id"]


def assert_uuid(value: str) -> None:
    UUID(value)


def seed_observability_rows(project_id: str) -> tuple[str, str]:
    sql = f"""
    WITH trace AS (
      INSERT INTO phase_traces (
        project_id,
        phase,
        trace_id,
        span_name,
        service_name,
        started_at,
        ended_at,
        duration_ms,
        status,
        metadata
      )
      VALUES (
        '{project_id}',
        'strategy',
        '11111111-1111-1111-1111-111111111111',
        'route-evidence',
        'retrieval-engine',
        '2026-01-01T00:00:00Z',
        '2026-01-01T00:00:02Z',
        2000,
        'success',
        '{{"mode":"hybrid"}}'::jsonb
      )
      RETURNING trace_id
    ),
    routing AS (
      INSERT INTO retrieval_routing_log (
        project_id,
        request_id,
        query,
        query_classification,
        mode,
        forced_hybrid,
        escalation_reason,
        confidence,
        item_count,
        gaps,
        created_at
      )
      VALUES (
        '{project_id}',
        '22222222-2222-2222-2222-222222222222',
        'market sizing evidence',
        'strategic',
        'hybrid',
        TRUE,
        'low_confidence',
        0.8200,
        7,
        '[{{"missing":"customer proof"}}]'::jsonb,
        '2026-01-01T00:00:03Z'
      )
      RETURNING request_id
    )
    INSERT INTO rubric_scores (
      project_id,
      phase,
      dimension,
      score_version,
      score,
      weight,
      evaluator_type,
      evaluator_model,
      blocking,
      threshold,
      trace_id,
      created_at
    )
    VALUES (
      '{project_id}',
      'strategy',
      'audience_alignment',
      1,
      4.25,
      0.4000,
      'deterministic',
      NULL,
      FALSE,
      3.50,
      (SELECT trace_id FROM trace),
      '2026-01-01T00:00:04Z'
    )
    RETURNING (SELECT trace_id FROM trace), (SELECT request_id FROM routing);
    """

    result = psql(sql)
    assert result.returncode == 0, result.stderr
    returned_rows = [line for line in result.stdout.splitlines() if "|" in line]
    assert returned_rows, result.stdout
    trace_id, request_id = returned_rows[0].strip().split("|")
    assert_uuid(trace_id)
    assert_uuid(request_id)
    return trace_id, request_id


def test_metrics_endpoint_returns_prometheus_snapshot():
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# TYPE pfos_projects_total counter" in response.text
    assert "pfos_open_outbox_items " in response.text
    assert "pfos_retrieval_routing_logs_total " in response.text


def test_traces_endpoint_returns_project_phase_traces():
    project_id = create_project("Observability Traces Project")
    trace_id, _ = seed_observability_rows(project_id)

    response = client.get(f"/traces/{project_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["traces"][0] == {
        "trace_id": trace_id,
        "phase": "strategy",
        "span_name": "route-evidence",
        "service_name": "retrieval-engine",
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:02Z",
        "duration_ms": 2000,
        "status": "success",
        "metadata": {"mode": "hybrid"},
    }


def test_retrieval_routing_endpoint_returns_project_logs():
    project_id = create_project("Observability Routing Project")
    _, request_id = seed_observability_rows(project_id)

    response = client.get(f"/observability/retrieval-routing/{project_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["routing_log_count"] == 1
    assert payload["routing_logs"][0] == {
        "request_id": request_id,
        "query": "market sizing evidence",
        "query_classification": "strategic",
        "mode": "hybrid",
        "forced_hybrid": True,
        "escalation_reason": "low_confidence",
        "confidence": 0.82,
        "item_count": 7,
        "gaps": [{"missing": "customer proof"}],
        "created_at": "2026-01-01T00:00:03Z",
    }


def test_rubric_endpoint_returns_phase_scores():
    project_id = create_project("Observability Rubric Project")
    trace_id, _ = seed_observability_rows(project_id)

    response = client.get(f"/observability/rubric/{project_id}/strategy")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["phase"] == "strategy"
    assert payload["score_count"] == 1
    assert payload["scores"][0] == {
        "dimension": "audience_alignment",
        "score_version": 1,
        "score": 4.25,
        "weight": 0.4,
        "evaluator_type": "deterministic",
        "evaluator_model": None,
        "blocking": False,
        "threshold": 3.5,
        "trace_id": trace_id,
        "created_at": "2026-01-01T00:00:04Z",
    }


def test_observability_endpoints_return_404_for_unknown_project():
    missing_project_id = "00000000-0000-0000-0000-000000000000"

    assert client.get(f"/traces/{missing_project_id}").status_code == 404
    assert client.get(f"/observability/retrieval-routing/{missing_project_id}").status_code == 404
    assert client.get(f"/observability/rubric/{missing_project_id}/strategy").status_code == 404
