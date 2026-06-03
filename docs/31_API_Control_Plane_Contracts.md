# API Control-Plane Contracts

This document summarizes the PFOS v3.2.4 workflow-service API/control-plane
surface that is implemented and covered by integration tests. PFOS v2 clean
integer step alignment is tracked in `docs/43_PFOS_v2_Clean_Integer_Step_Map.md`.
This document describes actual API behavior only; planned endpoints remain
marked as planned.

## Service Health

| Endpoint | Implemented | Contract test |
| --- | --- | --- |
| `GET /health` | Yes | `tests/integration/test_health_endpoint_normalization.py` |
| `GET /ready` | Yes | `tests/integration/test_health_endpoint_normalization.py` |

Both service probes are lightweight process-level checks. They intentionally do
not perform database, Docker, source lifecycle, or outbox dependency checks.

## Project Health Subresources

| Endpoint | Implemented | Contract test |
| --- | --- | --- |
| `GET /health/projects/{project_id}` | Yes | `tests/integration/test_project_health_endpoint.py` |
| `GET /health/projects/{project_id}/outbox` | Yes | `tests/integration/test_health_endpoint_normalization.py`, `tests/integration/test_source_retraction_status_e2e_hardening.py` |
| `GET /health/projects/{project_id}/source-retractions` | Yes | `tests/integration/test_health_endpoint_normalization.py`, `tests/integration/test_source_retraction_status_e2e_hardening.py` |
| `GET /health/projects/{project_id}/hard-gates` | Yes | `tests/integration/test_health_endpoint_normalization.py`, `tests/integration/test_review_approved_export_e2e.py`, `tests/integration/test_source_retraction_status_e2e_hardening.py` |

All project health endpoints verify project existence first and return `404`
with `detail.error = "project_not_found"` for unknown projects.

The aggregate project health endpoint is read-only. It composes project phase,
health score, evidence coverage, open retraction count, days in current phase,
approval velocity, blocking-gate status, and the existing outbox,
source-retraction, and hard-gate status payloads. Optional project repository
health helpers are used when present; otherwise the endpoint returns
deterministic fallback values without mutating project, outbox, source
lifecycle, approval, or hard-gate state.

## Project Lifecycle

| Endpoint | Implemented | Contract test |
| --- | --- | --- |
| `POST /projects` | Yes | `tests/integration/test_api_examples_contract.py`, `tests/integration/test_project_lifecycle_happy_path_e2e.py` |
| `POST /projects/{project_id}/phase-transitions` | Yes | `tests/integration/test_api_examples_contract.py`, `tests/integration/test_project_lifecycle_happy_path_e2e.py`, `tests/integration/test_review_approved_export_e2e.py` |

The tested happy path is:

1. `POST /projects` creates a project in `created`.
2. `created -> intake` applies with no guards.
3. `intake -> strategy` applies when deterministic rubric and thesis guards are
   satisfied and repository-backed hard gates are clean.

Phase transition requests remain blocked by existing outbox, retraction,
stale-artifact, blocking-rule, approval quorum, and export guards. The API tests
do not weaken or bypass guard semantics.

## Intake Chat Control Plane

| Endpoint | Implemented | Contract test |
| --- | --- | --- |
| `GET /projects/{project_id}/intake-chat/messages` | Yes | `tests/integration/test_chat_api.py`, `tests/integration/test_chat_intake_flow.py` |
| `POST /projects/{project_id}/intake-chat` | Yes | `tests/integration/test_chat_intake_flow.py` |
| `POST /projects/{project_id}/intake-chat/messages` | Yes | `tests/integration/test_chat_api.py`, `tests/integration/test_chat_intake_flow.py` |

Intake chat is project-scoped and append-only. `GET` verifies project existence,
returns messages ordered by `turn_index`, and supports bounded `limit` plus
`after_turn_index` pagination. Invalid bounds return `422` with
`detail.error = "invalid_chat_query"`.

`POST` accepts operator intake content only while the project is in `intake`.
Unknown projects return `404` with `detail.error = "project_not_found"` and
non-intake projects return `409` with `detail.error = "phase_mismatch"`.
Successful turns persist the user message, derive a deterministic structured
proposal through the intake orchestrator, append an assistant summary message,
and return the proposal. The proposal is advisory: it does not mutate project
fields or advance phase state.

## Approval Control Plane

| Endpoint | Implemented | Contract test |
| --- | --- | --- |
| `POST /projects/{project_id}/approvals` | Yes | `tests/integration/test_api_examples_contract.py`, `tests/integration/test_review_approved_export_e2e.py` |
| `GET /projects/{project_id}/approvals/status/{phase}` | Yes | `tests/integration/test_api_examples_contract.py`, `tests/integration/test_approval_status_endpoint.py` |

Review approval requires the phase-scoped quorum defined in
`docs/15_Human_Approval_Ledger.yaml`. `review -> approved` blocks without quorum
and passes after required partner and IC member approvals are present.

## Export Control Plane

`approved -> exported` reuses review approval quorum and re-runs export-time
guards. The tested exported path requires:

- `approval_quorum_met`
- `export_integrity`
- `no_pii_exposure`
- clean `no_blocking_rules`

Coverage: `tests/integration/test_review_approved_export_e2e.py`.

## Source Lifecycle Control Plane

| Endpoint or job | Implemented | Contract test |
| --- | --- | --- |
| `POST /sources/events` | Yes | `tests/integration/test_source_lifecycle_event_api.py`, `tests/integration/test_source_retraction_status_e2e_hardening.py` |
| `PATCH /sources/events/{event_id}/status` | Yes | `tests/integration/test_source_lifecycle_event_status_api.py` |
| `jobs.source_retraction_job` | Yes | `tests/integration/test_source_retraction_status_e2e_hardening.py` |
| `jobs.outbox_worker` | Yes | `tests/integration/test_source_retraction_status_e2e_hardening.py` |

The hardened source retraction E2E creates a retraction event through the API,
runs the existing source retraction job, verifies the project-scoped outbox row,
runs the existing outbox worker path project-scoped, and verifies source
retraction, outbox, and hard-gate health status return clean.

## Versioned Media Type

API examples and contract tests use:

```http
Accept: application/vnd.pfos.v3.2.4+json
Content-Type: application/vnd.pfos.v3.2.4+json
```

Local development may still accept `application/json`, but examples and
contract tests should keep the v3.2.4 media type visible.
