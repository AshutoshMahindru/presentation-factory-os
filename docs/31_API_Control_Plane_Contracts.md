# API Control-Plane Contracts

This document summarizes the PFOS v3.2.4 workflow-service API/control-plane
surface that is implemented and covered by integration tests after Baby Steps
66-71. It documents actual behavior only; planned endpoints remain marked as
planned.

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
| `GET /health/projects/{project_id}` | Planned | Not yet implemented |
| `GET /health/projects/{project_id}/outbox` | Yes | `tests/integration/test_health_endpoint_normalization.py`, `tests/integration/test_source_retraction_status_e2e_hardening.py` |
| `GET /health/projects/{project_id}/source-retractions` | Yes | `tests/integration/test_health_endpoint_normalization.py`, `tests/integration/test_source_retraction_status_e2e_hardening.py` |
| `GET /health/projects/{project_id}/hard-gates` | Yes | `tests/integration/test_health_endpoint_normalization.py`, `tests/integration/test_review_approved_export_e2e.py`, `tests/integration/test_source_retraction_status_e2e_hardening.py` |

All implemented project health subresources verify project existence first and
return `404` with `detail.error = "project_not_found"` for unknown projects.

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
