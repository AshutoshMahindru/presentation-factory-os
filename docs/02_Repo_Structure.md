# Repo Structure

## Runnable repository tree

```text
presentation-factory-os/
├── README.md
├── Makefile
├── docker-compose.yaml
├── docker/
│   ├── workflow-service.Dockerfile
│   ├── agent-service.Dockerfile
│   ├── retrieval-engine.Dockerfile
│   ├── tool-server.Dockerfile
│   ├── job-runner.Dockerfile
│   └── ui.Dockerfile
├── .env.example
├── pyproject.toml
├── package.json
├── docs/
│   ├── 00_README_v3.2.4.md
│   ├── 01_Runtime_Architecture.md
│   ├── 21_DesignTokens.schema.json
│   ├── 22_AudienceProfile.schema.json
│   ├── 23_Financial_Ingestion_Pipeline.yaml
│   ├── 24_API_Examples.md
│   └── ...
├── infra/
│   ├── postgres/
│   │   └── init/
│   │       └── 001_schema.sql
│   ├── neo4j/
│   │   └── constraints.cypher
│   ├── litellm/
│   │   └── config.yaml
│   └── qdrant/
│       └── collections.yaml
├── system/
│   ├── state_machine.py
│   ├── guards.py
│   ├── approval_quorum.py
│   ├── hard_gates.py
│   ├── provenance.py
│   └── config_loader.py
├── evidence_graph/
│   ├── constraints.py
│   ├── repository.py
│   ├── claim_service.py
│   ├── source_service.py
│   ├── lifecycle.py
│   └── cypher/
│       └── constraints.cypher
├── retrieval_engine/
│   ├── app.py
│   ├── router.py
│   ├── classifiers.py
│   ├── standard_payload.py
│   ├── graph_retriever.py
│   ├── semantic_retriever.py
│   ├── structured_retriever.py
│   └── logging.py
├── deck_builder/
│   ├── app.py
│   ├── slide_schema_validator.py
│   ├── render_pptxgenjs.ts
│   ├── render_python_pptx.py
│   ├── export_gate.py
│   ├── visual_qa.py
│   ├── narrative_arc_validator.py
│   └── templates/
│       ├── ic_grade_default.json
│       └── design_tokens.json
├── financial_model/
│   ├── repository.py
│   ├── validator.py
│   ├── formula_parser.py
│   ├── scenario_graph.py
│   ├── slide_numeric_assertion_checker.py
│   ├── ingestion_validator.py
│   └── schemas/
│       └── financial_model_schema.yaml
├── agents/
│   ├── app.py
│   ├── sdk.py
│   ├── base_agent.py
│   ├── intake_agent.py
│   ├── strategy_agent.py
│   ├── research_agent.py
│   ├── financial_agent.py
│   ├── narrative_agent.py
│   ├── visual_agent.py
│   └── review_agent.py
├── tool_server/
│   ├── app.py
│   ├── policy.py
│   ├── charts.py
│   ├── diagrams.py
│   ├── tables.py
│   ├── export.py
│   └── outputs/
├── jobs/
│   ├── scheduler.py
│   ├── source_scan_job.py
│   ├── source_retraction_job.py
│   ├── outbox_worker.py
│   ├── consolidation_job.py
│   └── weekly_health_job.py
├── api/
│   ├── workflow.py
│   ├── projects.py
│   ├── approvals.py
│   ├── exports.py
│   ├── sources.py
│   └── health.py
├── ui/
│   ├── app/
│   │   ├── page.tsx
│   │   ├── projects/[id]/page.tsx
│   │   ├── approvals/page.tsx
│   │   └── exports/page.tsx
│   ├── components/
│   │   ├── PhaseStepper.tsx
│   │   ├── RubricPanel.tsx
│   │   ├── ApprovalLedger.tsx
│   │   ├── EvidenceCoverage.tsx
│   │   ├── ProjectHealth.tsx
│   │   ├── StaleArtifactNotice.tsx
│   │   └── DeckPreview.tsx
│   └── lib/
│       └── api.ts
└── tests/
    ├── unit/
    │   ├── test_state_machine.py
    │   ├── test_claim_requires_source.py
    │   ├── test_retrieval_payload_schema.py
    │   ├── test_financial_validator.py
    │   ├── test_slide_schema.py
    │   ├── test_export_gate.py
    │   ├── test_quorum.py
    │   ├── test_no_agent_db_imports.py
    │   ├── test_numeric_assertions_require_financial_refs.py
    │   └── test_narrative_arc_validator.py
    ├── integration/
    │   ├── test_source_retraction_cascade.py
    │   ├── test_source_retraction_500_claims_async.py
    │   ├── test_outbox_eventual_consistency.py
    │   ├── test_outbox_neo4j_failure_retry_backoff.py
    │   ├── test_agent_network_isolation.py
    │   ├── test_retreat_archives_downstream_drafts.py
    │   ├── test_financial_ingestion_requires_ast.py
    │   ├── test_parser_provenance_required.py
    │   ├── test_visual_qa_blocks_approval.py
    │   ├── test_stale_artifact_ui_message.py
    │   ├── test_quorum.py
    │   ├── test_project_health_endpoint.py
    │   ├── test_end_to_end_brief_to_export.py
    │   ├── test_red_team_retraction_after_export.py
    │   └── test_cross_reference_consistency.py
    └── load/
        ├── test_outbox_queue_load.py
        └── test_source_retraction_queue_load.py
```

## Key files by subsystem

### `system/`

| File | Responsibility |
|---|---|
| `state_machine.py` | Loads `08_StateMachine_Spec.yaml`, validates transitions, applies retreat and reject paths |
| `guards.py` | Implements named guards such as `model_validated`, `evidence_coverage_ok`, `approval_quorum_met` |
| `approval_quorum.py` | Computes role-aware quorum and unanimity rules |
| `hard_gates.py` | Blocks unsupported financial claims, PII exposure, failed visual QA, and export integrity violations |

### `evidence_graph/`

| File | Responsibility |
|---|---|
| `claim_service.py` | Creates claims only after source existence and support edge are verified |
| `source_service.py` | Registers, updates, classifies, and retracts sources |
| `lifecycle.py` | Implements event-driven invalidation cascade and update migration |

### `retrieval_engine/`

| File | Responsibility |
|---|---|
| `router.py` | Chooses semantic, graph, structured, or hybrid retrieval |
| `standard_payload.py` | Emits `07_StandardContextPayload.schema.json` compliant responses |
| `logging.py` | Writes `retrieval_routing_log` and routing-misclassification metrics |

### `deck_builder/`

| File | Responsibility |
|---|---|
| `slide_schema_validator.py` | Validates slide jobs against `06_SlideJobDefinition.schema.json` |
| `visual_qa.py` | Runs deterministic and vision-model QA before approval |
| `export_gate.py` | Blocks degraded visuals, unvalidated finance, missing attribution, and integrity errors |

### `financial_model/`

| File | Responsibility |
|---|---|
| `validator.py` | Runs formula integrity, range, cross-scenario, and orphan checks |
| `slide_numeric_assertion_checker.py` | Requires `financial_refs` for numeric assertions in slide bodies |

### `agents/`

Agents use only `AgentSDK`. They have no direct database credentials and must fail CI if raw database drivers are imported.

### `tool_server/`

Tool server executes charts, diagrams, tables, and export fallbacks according to the degradation policy. Degraded output is explicit, logged, and blocked from final export when required.

### `tests/`

Tests are not optional. The repo is considered runnable only when CI validates schemas, SQL, YAML, state transitions, source enforcement, financial references, export gates, outbox retry/backoff, source-retraction batching, and agent DB isolation at both code and Docker-network levels.
