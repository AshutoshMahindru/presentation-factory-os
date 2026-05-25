# PFOS v3.2.4 Release Checklist

This checklist is the final release gate for PFOS v3.2.4. Run it from the
repository root after the release candidate branch has merged and before
publishing the v3.2.4 tag.

## Release Candidate Identity

- Release: `v3.2.4`
- Expected release branch: `main`
- Required local compose project: `pfos-dev`
- Required compose file: `docker-compose.apps.yaml`
- Required media type for API contract checks:
  `application/vnd.pfos.v3.2.4+json`

## Final Gate Checklist

| Gate | Command or evidence | Pass criteria |
| --- | --- | --- |
| Clean main | `git checkout main && git pull --ff-only && git status --short --branch` | On `main`, up to date with origin, no uncommitted or untracked release files. |
| Docker up | `make docker-up && make docker-ps` | `postgres`, `neo4j`, `qdrant`, `workflow-service`, `retrieval-engine`, `tool-server`, and `agent-service` are running under `pfos-dev`. |
| Schema loaded | `make validate-sql-live` | Postgres accepts `infra/postgres/init/001_schema.sql` and required tables exist. |
| `make validate` green | `make validate` | Compile, JSON schema validation, YAML validation, agent DB import guard, and pytest all pass. |
| `validate-live` green if available | `make validate-live` | Docker starts, SQL bootstrap succeeds, Docker doctor passes, and `make validate` passes. If local Docker is unavailable, record the reason and require equivalent CI/live evidence. |
| Source lifecycle/outbox smoke green | `DATABASE_URL=postgresql://pfos:pfos_dev_password@localhost:5432/pfos make smoke-source-lifecycle-outbox` and `PFOS_LIVE_DATABASE_URL=postgresql://pfos:pfos_dev_password@localhost:5432/pfos pytest tests/integration/test_source_lifecycle_outbox_live_smoke.py -vv` | Required queue tables are present, smoke is read-only, and row counts are unchanged by the live smoke test. |
| API/control-plane E2E green | `pytest tests/integration/test_workflow_api_postgres.py tests/integration/test_source_lifecycle_event_api.py tests/integration/test_approval_ledger_api.py tests/integration/test_workflow_outbox_gate.py -vv` | Project creation, phase transition, approval ledger, source lifecycle API, and outbox hard-gate paths pass against the expected backing stores or test fixtures. |
| Deck/export E2E green | `pytest tests/unit/test_slide_schema.py tests/unit/test_narrative_arc_validator.py tests/unit/test_export_gate.py tests/unit/test_numeric_assertions_require_financial_refs.py tests/unit/test_render_python_pptx.py tests/integration/test_end_to_end_brief_to_export.py tests/integration/test_review_approved_export_e2e.py -vv` | Schema, narrative, export gate, numeric assertion checks, deterministic outline artifact metadata, brief-to-export, and approved-export paths pass. |
| UI operator path documented | Operator evidence references `ui/components/ApprovalLedger.tsx`, `ui/components/ProjectHealth.tsx`, `ui/components/PhaseStepper.tsx`, `ui/components/DeckPreview.tsx`, `ui/components/EvidenceCoverage.tsx`, `ui/components/RubricPanel.tsx`, and `ui/components/StaleArtifactNotice.tsx`. | The documented operator path covers project phase, health, evidence coverage, rubric status, approval/quorum state, deck preview, and stale-artifact messaging. |
| Observability endpoints green | `pytest tests/integration/test_health_endpoint_normalization.py tests/integration/test_source_retraction_status_endpoint.py tests/integration/test_hard_gate_status_endpoint.py tests/integration/test_approval_status_endpoint.py -vv` | `/health`, `/ready`, source retraction status, hard-gate status, and approval status endpoints return stable response contracts. |
| Load tests green | `pytest tests/load -vv` plus release evidence for the thresholds in `docs/19_Implementation_Plan_v3.2.4.md`. | Outbox queue recovers from 50 concurrent unprocessed rows within 60 seconds after Neo4j recovery, and source retraction blocking/cascade thresholds meet the v3.2.4 plan in an isolated Docker-backed database. |
| Demo seed project works | `python3 scripts/seed_demo_project.py` for fixture validation; with the stack running, `python3 scripts/seed_demo_project.py --api-base-url http://localhost:8000` followed by the operator checks in `docs/36_Demo_Seed_Project.md`. | The canonical seed fixture validates locally, loads through `POST /projects`, returns a created project with a valid audience profile, and can be inspected through health/status endpoints without manual database edits. |
| Known limitations / deferred items recorded | Update the release notes or PR body from the list below. | No deferred item is hidden; every non-green or placeholder gate has an owner and follow-up step before final tag approval. |
| Final git tag recommendation | `git tag -a v3.2.4 -m "PFOS v3.2.4" && git push origin v3.2.4` | Tag only after this checklist is green or explicitly approved with documented deferrals. |

## Known Limitations And Deferred Items

- No checked-in `.github/workflows` directory is present in this checkout, so
  CI parity is documented but not enforced by a repository workflow.
- `make validate-live` is available locally, but it depends on Docker and the
  canonical `pfos-dev` compose environment.
- `GET /health/projects/{project_id}` aggregate health remains planned; the
  implemented release surface is `/health`, `/ready`, and project health
  subresources.
- Deck/export renderer orchestration is only partially complete. The current
  release surface includes deterministic outline artifact metadata, but full
  PPTX/API export orchestration remains a deferred hardening item.
- Load tests require an isolated Docker-backed database. Stale queue rows from
  earlier local runs can invalidate source-retraction load-test evidence and
  should be cleared with the documented Docker reset before final release
  validation.
- SQL and Cypher executable validation sources have documented drift between
  `docs/` specifications and `infra/` runtime bootstrap files; choose and
  enforce a canonical source before treating schema validation as release
  complete.

## Release Decision

The recommended tag is `v3.2.4`.

Do not create or push the tag until:

1. `main` is clean and up to date.
2. Docker-backed schema and live validation have passed or an equivalent release
   environment has recorded evidence.
3. `make validate` is green.
4. API/control-plane, source lifecycle/outbox, observability, deck/export,
   load-test, UI operator, and demo seed gates are either green or explicitly
   accepted as deferred release limitations.
