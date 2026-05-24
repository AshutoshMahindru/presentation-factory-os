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
| `GET /health/projects/{project_id}` | Planned | `api/health.py` placeholder | Aggregate project health score and dashboard payload. | Not yet implemented |
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

Implemented project health subresources first verify that the project exists.
Unknown projects return:

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

## Deferred Aggregate Endpoint

`GET /health/projects/{project_id}` remains planned rather than normalized in
this step. The v3.2.4 plan calls for an aggregate payload with health score,
evidence coverage, open retractions, days in phase, approval velocity, and
blocking-gate status. Those aggregate semantics are not yet implemented in the
codebase, and adding them would require new scoring and repository contracts
beyond this low-risk normalization step.

## Compatibility Notes

- `/ready` is a probe-only compatibility alias and does not perform dependency
  checks.
- `/health/projects/{project_id}/outbox` reuses the already-centralized outbox
  status repository and does not alter outbox worker behavior.
- `/health/projects/{project_id}/source-retractions` and
  `/health/projects/{project_id}/hard-gates` retain their existing response
  contracts.
- `api/health.py` is still an empty placeholder for the future aggregate
  project health implementation.
