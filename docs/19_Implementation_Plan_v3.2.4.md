# Implementation Plan v3.2.4

This release should be planned as a five-to-six-week implementation, not a four-week sprint. v3.2.4 adds infrastructure-enforced agent isolation, outbox eventual consistency, async source-retraction cascades, deterministic financial ingestion, visual QA, approval UI, project health, end-to-end tests, and load-test thresholds. Compressing that scope into four weeks creates execution risk.

## Week 1: Skeleton + Infrastructure Enforcement

### Build

- Docker compose stack with Postgres, Neo4j, Qdrant, LiteLLM, workflow service, retrieval engine, tool server, agent service, job runner, and UI.
- Explicit Docker network isolation: `agent-service` attaches only to `pfos_agent_runtime`; it has no routable network path to Postgres, Neo4j, or Qdrant.
- `evidence_graph/constraints.py` to apply Neo4j constraints and indexes.
- `system/state_machine.py` to load `08_StateMachine_Spec.yaml` and reject invalid transitions.
- `api/workflow.py` with project creation, phase transition, provenance, and guard-result endpoints.
- Postgres schema initialization from `04_Database_Schemas.sql`.
- `22_AudienceProfile.schema.json` codegen and project creation validation for `audience_profile`.

### Acceptance

- Cannot create a claim without an active source.
- Valid transitions pass.
- Invalid transitions fail.
- `intake -> strategy` fails if `audience_profile` is incomplete or schema-invalid.
- Retreat transitions require reason.
- Rejected and exported phases are terminal.
- `agent-service` cannot resolve or connect to Postgres, Neo4j, or Qdrant by Docker service name.

### Tests

- `tests/unit/test_state_machine.py`
- `tests/unit/test_claim_requires_source.py`
- `tests/unit/test_no_agent_db_imports.py`
- `tests/integration/test_agent_network_isolation.py`

## Week 2: Outbox + Retrieval + Agents

### Build

- Postgres outbox writer in workflow-service.
- Job-runner outbox poller with idempotent Neo4j writes, retry counters, and backoff schedule.
- Unified retrieval engine with semantic, graph, structured, and hybrid modes.
- Routing validation for financial, strategic, narrative, visual, and unknown query classes.
- `AgentSDK` with RetrievalClient, ToolClient, LLMClient, and WorkflowClient.
- Tool fallbacks for charts, diagrams, and tables.

### Acceptance

- Financial query routes to structured or hybrid.
- Strategic contradiction query routes to graph or hybrid.
- Unknown low-confidence query emits a gap and recommended next action.
- Outbox rows block phase transition until processed or explicitly resolved.
- Simulated Neo4j outage causes outbox retry/backoff, then eventual success after recovery.

### Tests

- `tests/unit/test_retrieval_payload_schema.py`
- `tests/unit/test_slide_schema.py`
- `tests/integration/test_outbox_eventual_consistency.py`
- `tests/integration/test_outbox_neo4j_failure_retry_backoff.py`

## Week 3: Financial Ingestion + Financial Model Validation

### Build

- Tool-server `/tools/parse_excel_ast` using deterministic formula-aware parsing.
- `23_Financial_Ingestion_Pipeline.yaml` implementation.
- Financial model repository and validator around the standardized `financial_cells` table.
- Parser provenance allow-list enforcement.
- Numeric assertion checker for slide bodies.

### Acceptance

- Excel-origin financial cells cannot be inserted without parser provenance.
- LLM agents cannot directly call `pandas.read_excel()` or `xlwings` to infer formulas.
- Unmoored numbers in slide body are rejected unless `financial_refs` exist.
- Circular references, missing dependencies, and non-namespaced cell refs are blocking.

### Tests

- `tests/unit/test_financial_validator.py`
- `tests/integration/test_financial_ingestion_requires_ast.py`
- `tests/integration/test_parser_provenance_required.py`
- `tests/unit/test_numeric_assertions_require_financial_refs.py`

## Week 4: Deck + Narrative + Visual QA + Export Gate

### Build

- Deck builder slide validation against `06_SlideJobDefinition.schema.json`.
- `deck_builder/narrative_arc_validator.py` for deterministic slide order, request-decision placement, and objection-preemption checks.
- Renderers: `pptxgenjs`, `python_pptx`, and outline fallback.
- Visual QA agent with screenshot-based checks.
- Rubric engine implementation using deterministic, heuristic, graph-query, and judge dimensions.
- Export endpoint with hard gates.
- UI `StaleArtifactNotice` component for `stale_due_to_retreat` artifacts.

### Acceptance

- Degraded slides block export.
- Visual QA below 4 blocks approval.
- Missing source attribution blocks review.
- Invalid narrative arc blocks narrative-to-visual-design progression.
- Unvalidated financial calculations block approval and export.
- Export integrity check confirms slide count, media references, source appendix, and financial reference map.
- UI communicates stale artifacts with: “This slide was drafted before the financial model was revised and requires revalidation.”

### Tests

- `tests/unit/test_export_gate.py`
- `tests/unit/test_slide_schema.py`
- `tests/unit/test_narrative_arc_validator.py`
- `tests/integration/test_visual_qa_blocks_approval.py`
- `tests/integration/test_stale_artifact_ui_message.py`

## Week 5: Source Lifecycle + Approval UI + Project Health

### Build

- Source lifecycle job with event-driven and weekly cron modes.
- Async batched source-retraction cascade with 50-claim transaction batches.
- Manual API and HMAC webhook for source events.
- Approval UI with ledger timeline, quorum status, dissent visibility, escalation state, and read-only project health dashboard.
- `/health/projects/{project_id}` aggregation endpoint.

### Acceptance

- Retraction marks affected projects blocked immediately.
- Standard 500-claim cascade completes within 30 seconds under normal operating conditions.
- Batch cascade completes without large Neo4j lock contention.
- UI shows dissent and missing quorum roles.
- Approval ledger is immutable.
- `/health/projects/{project_id}` returns health score, evidence coverage, open retractions, days in phase, approval velocity, and blocking-gate status.

### Tests

- `tests/integration/test_source_retraction_cascade.py`
- `tests/integration/test_source_retraction_500_claims_async.py`
- `tests/integration/test_quorum.py`
- `tests/integration/test_project_health_endpoint.py`

## Week 6: E2E Hardening + Red-Team Scenarios

### Build

- Consolidation job for memory cleanup and provenance deduplication.
- End-to-end test from brief to export.
- Red-team retraction scenario against an already exported deck.
- Load test for outbox and source cascade queues.
- Implementation-readiness review against `20_Cross_Reference_Matrix.md`.

### Load test thresholds

- Outbox queue: 50 concurrent unprocessed outbox items during transient Neo4j failure; after Neo4j recovery, all items must drain within 60 seconds with zero failed rows.
- Source retraction queue: 100 concurrent source retractions, each with up to 500 supported claims; affected projects must be blocked within 5 seconds; each standard 500-claim cascade must complete within 30 seconds using batch size 50.

### Acceptance

- End-to-end workflow can create a project, pass phase gates, approve, export, retract a source, block affected project, and show the blocking state in UI.
- Exported deck affected by source retraction triggers critical alert.
- Outbox and source retraction queues recover from transient Neo4j failure.
- Cross-reference checklist passes.

### Tests

- `tests/integration/test_end_to_end_brief_to_export.py`
- `tests/integration/test_red_team_retraction_after_export.py`
- `tests/load/test_outbox_queue_load.py`
- `tests/load/test_source_retraction_queue_load.py`
- `tests/integration/test_cross_reference_consistency.py`

## Definition of done

A build is v3.2.4-complete when:

1. The repo starts with `docker compose up`.
2. Schemas validate in CI.
3. Agents have no DB credentials, no DB imports, and no Docker network path to data stores.
4. State-machine transitions are deterministic and audited.
5. Claims cannot exist without active source support.
6. Financial cells are formula-backed and parser-provenance-enforced.
7. Numeric slide assertions require financial references.
8. Degraded visuals cannot be exported.
9. Source retractions cascade asynchronously and block affected projects.
10. Standard 500-claim retraction cascades target a 30-second operational SLA, with affected projects blocked immediately and remaining blocked until queue completion.
11. Outbox eventual consistency is tested against Neo4j failure and retry/backoff.
12. Human approvals are ledger-based, quorum-aware, and phase-scoped.
13. Audience psychology is structured, schema-validated, and transition-gated.
14. Narrative arc validation is deterministic and does not add a new phase.
15. Project health dashboard is read-only and does not directly drive phase transitions.
16. Phase-name enums are synchronized across SQL, YAML, generated code, API validators, and UI labels.
17. API contract tests use `application/vnd.pfos.v3.2.4+json`.
