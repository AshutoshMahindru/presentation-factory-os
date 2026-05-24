# Baby Step Command

The goal of baby step 1 is to create a runnable skeleton that already reflects the architecture: services, schemas, validation surfaces, and tests. It does not yet need full business logic.

```bash
# 1. Create repo root
mkdir -p presentation-factory-os-v3_2_4
cd presentation-factory-os-v3_2_4

# 2. Create executable subsystem directories
mkdir -p \
  docs \
  docker \
  infra/postgres/init \
  infra/neo4j \
  infra/litellm \
  infra/qdrant \
  system \
  evidence_graph/cypher \
  retrieval_engine \
  deck_builder/templates \
  financial_model/schemas \
  agents \
  tool_server/outputs \
  jobs \
  api \
  ui/app/projects/[id] \
  ui/app/approvals \
  ui/app/exports \
  ui/components \
  ui/lib \
  tests/unit \
  tests/integration \
  tests/load

# 3. Create top-level runtime files
touch README.md Makefile docker-compose.yaml .env.example pyproject.toml package.json

# 4. Create infrastructure and Docker build files
touch docker/workflow-service.Dockerfile docker/agent-service.Dockerfile docker/retrieval-engine.Dockerfile docker/tool-server.Dockerfile docker/job-runner.Dockerfile docker/ui.Dockerfile
touch infra/postgres/init/001_schema.sql
touch infra/neo4j/constraints.cypher
touch infra/litellm/config.yaml
touch infra/qdrant/collections.yaml


# 4a. Create document schema files used by CI/codegen
touch docs/06_SlideJobDefinition.schema.json docs/07_StandardContextPayload.schema.json docs/21_DesignTokens.schema.json docs/22_AudienceProfile.schema.json docs/23_Financial_Ingestion_Pipeline.yaml docs/24_API_Examples.md

# 5. Create deterministic system layer
touch system/__init__.py
touch system/state_machine.py system/guards.py system/approval_quorum.py system/hard_gates.py system/provenance.py system/config_loader.py

# 6. Create evidence graph layer
touch evidence_graph/__init__.py
touch evidence_graph/constraints.py evidence_graph/repository.py evidence_graph/claim_service.py evidence_graph/source_service.py evidence_graph/lifecycle.py

# 7. Create retrieval engine layer
touch retrieval_engine/__init__.py
touch retrieval_engine/app.py retrieval_engine/router.py retrieval_engine/classifiers.py retrieval_engine/standard_payload.py retrieval_engine/graph_retriever.py retrieval_engine/semantic_retriever.py retrieval_engine/structured_retriever.py retrieval_engine/logging.py

# 8. Create deck builder layer
touch deck_builder/__init__.py
touch deck_builder/app.py deck_builder/slide_schema_validator.py deck_builder/render_python_pptx.py deck_builder/export_gate.py deck_builder/visual_qa.py deck_builder/render_pptxgenjs.ts deck_builder/narrative_arc_validator.py

# 9. Create financial model layer
touch financial_model/__init__.py
touch financial_model/repository.py financial_model/validator.py financial_model/formula_parser.py financial_model/scenario_graph.py financial_model/slide_numeric_assertion_checker.py financial_model/ingestion_validator.py

# 10. Create agent SDK and agent shells
touch agents/__init__.py
touch agents/app.py agents/sdk.py agents/base_agent.py agents/intake_agent.py agents/strategy_agent.py agents/research_agent.py agents/financial_agent.py agents/narrative_agent.py agents/visual_agent.py agents/review_agent.py

# 11. Create tool server and jobs
touch tool_server/__init__.py
touch tool_server/app.py tool_server/policy.py tool_server/charts.py tool_server/diagrams.py tool_server/tables.py tool_server/export.py
touch jobs/__init__.py jobs/scheduler.py jobs/source_scan_job.py jobs/source_retraction_job.py jobs/outbox_worker.py jobs/consolidation_job.py jobs/weekly_health_job.py

# 12. Create API shells
touch api/__init__.py api/workflow.py api/projects.py api/approvals.py api/exports.py api/sources.py api/health.py

# 13. Create UI shells
touch ui/app/page.tsx ui/app/projects/[id]/page.tsx ui/app/approvals/page.tsx ui/app/exports/page.tsx
touch ui/components/PhaseStepper.tsx ui/components/RubricPanel.tsx ui/components/ApprovalLedger.tsx ui/components/EvidenceCoverage.tsx ui/components/ProjectHealth.tsx ui/components/StaleArtifactNotice.tsx ui/components/DeckPreview.tsx
touch ui/lib/api.ts

# 14. Create tests first
# Unit tests from Week 1-4 readiness plan
touch tests/unit/test_state_machine.py tests/unit/test_claim_requires_source.py tests/unit/test_retrieval_payload_schema.py tests/unit/test_financial_validator.py tests/unit/test_slide_schema.py tests/unit/test_export_gate.py tests/unit/test_quorum.py tests/unit/test_no_agent_db_imports.py tests/unit/test_numeric_assertions_require_financial_refs.py tests/unit/test_narrative_arc_validator.py

# Integration tests from Week 1-6 readiness plan
touch tests/integration/test_source_retraction_cascade.py tests/integration/test_source_retraction_500_claims_async.py tests/integration/test_outbox_eventual_consistency.py tests/integration/test_outbox_neo4j_failure_retry_backoff.py tests/integration/test_agent_network_isolation.py tests/integration/test_retreat_archives_downstream_drafts.py tests/integration/test_financial_ingestion_requires_ast.py tests/integration/test_parser_provenance_required.py tests/integration/test_visual_qa_blocks_approval.py tests/integration/test_stale_artifact_ui_message.py tests/integration/test_quorum.py tests/integration/test_project_health_endpoint.py tests/integration/test_end_to_end_brief_to_export.py tests/integration/test_red_team_retraction_after_export.py tests/integration/test_cross_reference_consistency.py

# Load tests from Week 6 readiness plan
touch tests/load/test_outbox_queue_load.py tests/load/test_source_retraction_queue_load.py
> Test scaffold policy: the baby step creates the full named test surface from the implementation plan. Test bodies are intentionally added iteratively as the services come online; paths should not drift from `19_Implementation_Plan_v3.2.4.md` or `18_CI_CD_Schema_Validation.md`.


# 15. Confirm tree
find . -maxdepth 3 -type f | sort
```

## Next steps after the command

1. Copy `04_Database_Schemas.sql` into `infra/postgres/init/001_schema.sql`.
2. Copy `05_Evidence_Graph_Cypher.cypher` into `infra/neo4j/constraints.cypher`.
3. Copy `10_Model_Proxy_Config.yaml` into `infra/litellm/config.yaml`.
4. Copy `16_Docker_Compose_Complete.yaml` into `docker-compose.yaml`; confirm the `agent-service` container is present and restricted to workflow-service, retrieval-engine, tool-server, and litellm-proxy egress; confirm the UI service uses `docker/ui.Dockerfile` from the repo-root build context.
5. Implement one vertical slice before expanding: create project → add source → create supported claim → transition intake to strategy → reject invalid transition.

## Baby-step acceptance

The repo is ready for implementation when these checks pass:

```bash
python -m compileall system evidence_graph retrieval_engine financial_model agents tool_server jobs api
pytest tests/unit/test_no_agent_db_imports.py
pytest tests/integration/test_agent_network_isolation.py
```
