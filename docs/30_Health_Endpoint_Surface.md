# Health Endpoint Surface

Baby Step 66 audits the PFOS v3.2.4 control-plane health endpoints and
normalizes only the low-risk parts that already have deterministic repository
support. These endpoints are read-only and must not mutate source lifecycle,
outbox worker, Docker, Makefile, or schema behavior.

## Endpoint Inventory

| Endpoint | Status | Owner | Purpose | Dependencies |
| --- | --- | --- | --- | --- |
| `GET /health` | Implemented | `api/workflow.py` | Lightweight liveness response for the workflow service. | None |
| `GET /ready` | Implemented | `api/workflow.py` | Lightweight readiness response for local orchestration and probes. | None |
| `GET /health/projects/{project_id}` | Implemented | `api/workflow.py` | Aggregate project health score and dashboard payload. | `ProjectRepository`, `OutboxRepository.get_project_outbox_status`, `SourceLifecycleRepository.get_project_retraction_cascade_status`, `HardGateRepository.evaluate_no_blocking_rules` |
| `GET /health/projects/{project_id}/outbox` | Implemented | `api/workflow.py` | Project-scoped outbox blocking status. | `OutboxRepository.get_project_outbox_status` |
| `GET /health/projects/{project_id}/source-retractions` | Implemented | `api/workflow.py` | Project-scoped source retraction cascade status. | `SourceLifecycleRepository.get_project_retraction_cascade_status` |
| `GET /health/projects/{project_id}/hard-gates` | Implemented | `api/workflow.py` | Project-scoped `no_blocking_rules` hard-gate bundle status. | `HardGateRepository.evaluate_no_blocking_rules` |

## Normalized Behavior

### Service Probes

`GET /health` returns:

```json
{
  "service": "workflow-service",
  "status": "ok"
}
```

`GET /ready` returns:

```json
{
  "service": "workflow-service",
  "status": "ready"
}
```

These probes intentionally avoid database, Docker, source lifecycle, outbox, or
schema checks. Operational Docker validation remains covered by the local Docker
runbook and `make validate`.

### Project Subresources

Project health endpoints first verify that the project exists. Unknown projects
return:

```json
{
  "detail": {
    "error": "project_not_found"
  }
}
```

The outbox endpoint returns the existing centralized status shape:

```json
{
  "project_id": "project-id",
  "blocked": false,
  "unprocessed_count": 0,
  "failed_count": 0,
  "oldest_unprocessed_age_seconds": null
}
```

The source-retraction endpoint returns:

```json
{
  "project_id": "project-id",
  "blocked": false,
  "pending_count": 0,
  "processing_count": 0,
  "failed_count": 0,
  "oldest_open_age_seconds": null
}
```

The hard-gates endpoint returns the `no_blocking_rules` bundle with `checks` and
`failed_checks` arrays. Each check carries a stable `name`, pass/fail state,
optional `reason`, and metadata from the underlying repository.

### Aggregate Project Health

`GET /health/projects/{project_id}` is read-only and composes the existing
project health subresources into a dashboard payload:

```json
{
  "project_id": "project-id",
  "current_phase": "review",
  "status": "ready",
  "blocked": false,
  "health_score": 1.0,
  "evidence_coverage_ratio": 1.0,
  "evidence_coverage": {
    "ratio": 1.0,
    "covered_count": null,
    "total_count": null,
    "source": "deterministic_fallback"
  },
  "open_retractions": 0,
  "days_in_current_phase": 0,
  "approval_velocity": {
    "approvals_per_day": 0.0,
    "approval_count": 0,
    "days_in_phase": 0,
    "source": "deterministic_fallback"
  },
  "blocking_gates_status": "clear",
  "outbox": {
    "project_id": "project-id",
    "blocked": false,
    "unprocessed_count": 0,
    "failed_count": 0,
    "oldest_unprocessed_age_seconds": null
  },
  "source_retractions": {
    "project_id": "project-id",
    "blocked": false,
    "pending_count": 0,
    "processing_count": 0,
    "failed_count": 0,
    "oldest_open_age_seconds": null
  },
  "hard_gates": {
    "project_id": "project-id",
    "name": "no_blocking_rules",
    "passed": true,
    "checks": [],
    "failed_checks": []
  }
}
```

When optional project repository health helpers are present, the endpoint uses
them for evidence coverage, days in current phase, approval velocity, and health
score. Otherwise it keeps deterministic fallbacks: evidence coverage is treated
as neutral, days in phase is `0`, approval velocity is `0`, and missing optional
metrics are neutral in the derived score while existing outbox, retraction,
approval, and hard-gate status still contribute.

## Compatibility Notes

- `/ready` is a probe-only compatibility alias and does not perform dependency
  checks.
- `/health/projects/{project_id}/outbox` reuses the already-centralized outbox
  status repository and does not alter outbox worker behavior.
- `/health/projects/{project_id}/source-retractions` and
  `/health/projects/{project_id}/hard-gates` retain their existing response
  contracts.
- `/health/projects/{project_id}` embeds the subresource payloads and does not
  mutate project, outbox, source lifecycle, approval, or hard-gate state.

## Contract Coverage

The implemented health surface is covered by:

- `tests/integration/test_health_endpoint_normalization.py`
- `tests/integration/test_project_health_endpoint.py`
- `tests/integration/test_source_retraction_status_e2e_hardening.py`
