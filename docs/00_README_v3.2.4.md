# Presentation Factory OS v3.2.4

Runnable repo-first AI OS for IC-grade presentations.

## Core correction from v3

v3 was a skeleton. v3.2.4 provides organs: a complete state machine with retreat transitions, an adversarial rubric engine, a financial model schema, an event-driven source lifecycle, a multi-party human approval ledger, an executable agent-service runtime, materiality-based export gating, and CI validation for SQL, JSON Schema, YAML, and Cypher, plus constrained audience psychology and deterministic narrative arc validation.

## Operating doctrine

Presentation Factory OS is not a folder convention. It is a constrained production system where every important principle is executable through schema, service contracts, state-machine guards, network boundaries, tests, or export gates.

## Principle-to-Enforcement Map

| # | Principle | Enforcement files | Runtime mechanism |
|---|---|---|---|
| 1 | Replace policy with constraints | `04_Database_Schemas.sql`, `08_StateMachine_Spec.yaml`, `06_SlideJobDefinition.schema.json` | CHECK constraints, FK references, JSON Schema validation, state-machine guards |
| 2 | Separate deterministic orchestration from probabilistic generation | `01_Runtime_Architecture.md`, `11_Agent_SDK_Spec.md`, `16_Docker_Compose_Complete.yaml` | Workflow service owns transitions; agent-service generates only through SDK clients |
| 3 | Financial truth must be formula-backed | `04_Database_Schemas.sql`, `09_Financial_Model_Schema.yaml` | `formula NOT NULL`, composite financial cell identity, validation pipeline, numeric-claim slide gate |
| 4 | Evidence must precede claims | `05_Evidence_Graph_Cypher.cypher`, `13_Source_Lifecycle_Spec.yaml` | Claims require a matched source and `SUPPORTED_BY` edge; source retractions cascade with two-source support threshold |
| 5 | Provenance is mandatory | `04_Database_Schemas.sql`, `07_StandardContextPayload.schema.json`, `17_Observability_Spec.yaml` | Provenance table, retrieval provenance block, trace IDs, request IDs |
| 6 | Humans approve as a ledger, not a boolean | `15_Human_Approval_Ledger.yaml`, `08_StateMachine_Spec.yaml` | Immutable approval events, quorum computation, role-aware approval gates |
| 7 | Degradation is allowed, but unsafe shipment is blocked | `12_Tool_Server_Degradation_Policy.yaml`, `06_SlideJobDefinition.schema.json`, `08_StateMachine_Spec.yaml` | Fallback ladders, materiality enum, degraded visual blockers, export integrity hard gate |
| 8 | Routing and evaluation must be observable | `07_StandardContextPayload.schema.json`, `14_Rubric_Engine_Spec.yaml`, `17_Observability_Spec.yaml` | Routing logs, rubric scores, phase traces, alerts, fallback counters, project health score |
| 9 | Audience psychology must be structured, not prose | `04_Database_Schemas.sql`, `22_AudienceProfile.schema.json`, `08_StateMachine_Spec.yaml`, `14_Rubric_Engine_Spec.yaml` | JSONB object check, schema codegen, intake-to-strategy guard, audience adequacy scoring cap |
| 10 | Narrative architecture is validated without adding a phase | `06_SlideJobDefinition.schema.json`, `14_Rubric_Engine_Spec.yaml`, `deck_builder/narrative_arc_validator.py` | Narrative arc enum, deterministic slide sequence checks, objection-preemption map |
| 11 | Agent DB isolation is infrastructure-enforced | `16_Docker_Compose_Complete.yaml`, `01_Runtime_Architecture.md`, `11_Agent_SDK_Spec.md` | `agent-service` has no Docker network route to Postgres, Neo4j, or Qdrant |
| 12 | Cross-store writes are eventually consistent and blocking | `04_Database_Schemas.sql`, `08_StateMachine_Spec.yaml`, `17_Observability_Spec.yaml` | Outbox rows block transitions until processed; retry/backoff is tested against Neo4j failure |

## Immediate start commands

```bash
mkdir presentation-factory-os-v3_2_4
cd presentation-factory-os-v3_2_4
cp docs/16_Docker_Compose_Complete.yaml docker-compose.yaml
cp docs/04_Database_Schemas.sql infra/postgres/init/001_schema.sql
cp docs/10_Model_Proxy_Config.yaml infra/litellm/config.yaml
docker compose up -d postgres neo4j qdrant litellm-proxy workflow-service retrieval-engine tool-server agent-service
make validate
make test
```

For baby-step bootstrapping from an empty directory, run the commands in `03_Baby_Step_Command.md`.

## Document inventory

| File | Purpose |
|---|---|
| `00_README_v3.2.4.md` | System overview, correction from v3, principle enforcement map, inventory |
| `01_Runtime_Architecture.md` | Service graph, network contracts, sovereignty rule |
| `02_Repo_Structure.md` | Runnable repo tree and key files |
| `03_Baby_Step_Command.md` | Bash commands to create the skeleton and first files |
| `04_Database_Schemas.sql` | PostgreSQL 16 schema and constraints |
| `05_Evidence_Graph_Cypher.cypher` | Neo4j constraints, indexes, and enforcement patterns |
| `06_SlideJobDefinition.schema.json` | JSON Schema for individual slide jobs, including materiality |
| `07_StandardContextPayload.schema.json` | JSON Schema for retrieval-engine output |
| `08_StateMachine_Spec.yaml` | Phase states, forward/retreat/reject transitions, hard gates, quorum rules |
| `09_Financial_Model_Schema.yaml` | Financial cell and scenario validation model |
| `10_Model_Proxy_Config.yaml` | LiteLLM local/remote routing config |
| `11_Agent_SDK_Spec.md` | Agent SDK contract, HTTP-only client policy, DB-access ban |
| `12_Tool_Server_Degradation_Policy.yaml` | Tool fallback ladders, materiality policy, and blocking rules |
| `13_Source_Lifecycle_Spec.yaml` | Source events, update/retraction cascade, job config |
| `14_Rubric_Engine_Spec.yaml` | Phase-level scoring, blockers, judge isolation |
| `15_Human_Approval_Ledger.yaml` | Multi-party approval ledger and quorum computation |
| `16_Docker_Compose_Complete.yaml` | Full local compose stack including agent-service |
| `17_Observability_Spec.yaml` | Metrics, traces, alerts, endpoints |
| `18_CI_CD_Schema_Validation.md` | GitHub Actions, Makefile targets, CI rules |
| `19_Implementation_Plan_v3.2.4.md` | Five-to-six-week implementation plan and acceptance criteria |
| `20_Cross_Reference_Matrix.md` | Principle/file/service consistency matrix |
| `21_DesignTokens.schema.json` | JSON Schema for design token payload shape |
| `22_AudienceProfile.schema.json` | JSON Schema for IC audience psychology and stakeholder mapping |
| `23_Financial_Ingestion_Pipeline.yaml` | Deterministic Excel/CSV/manual/API ingestion boundary for formula-backed financial cells |
| `24_API_Examples.md` | Example payloads for project creation, phase transitions, and approval submission |
| `30_Health_Endpoint_Surface.md` | Implemented and planned workflow-service health endpoints |
| `31_API_Control_Plane_Contracts.md` | API/control-plane endpoint contract map and test coverage |

## v3.2.4 scope decisions

- Approved: constrained audience psychology via `audience_profile`, `22_AudienceProfile.schema.json`, the `audience_psychology_adequate` guard, and rubric scoring.
- Approved: deterministic narrative arc validation without adding a new state-machine phase.
- Approved: expanded rubric dimensions for audience psychology and visual narrative alignment.
- Approved: read-only project health dashboard based on existing deterministic metrics.
- Deferred to v3.3.0: cross-project memory. It requires organization-level sovereignty, classification-bleed controls, derived-pattern-only sharing, and shared-memory consent before it can be safely introduced.
- Affirmed permanently: Agent SDK database isolation remains a load-bearing boundary and must not be relaxed.


- Added in v3.2.4: Docker-network isolation for `agent-service`, phase-scoped approval quorum semantics, canonical `financial_cells` table naming, API payload examples, outbox retry/backoff integration-test requirements, phase enum synchronization checklist, and a five-to-six-week implementation plan.


## Implementation patch assets

| Path | Purpose |
|---|---|
| `ui/components/StaleArtifactNotice.tsx` | User-facing warning component using exactly the `stale_due_to_retreat` copy from `12_Tool_Server_Degradation_Policy.yaml`. |
| `tests/integration/test_agent_network_isolation.py` | TCP-level verification that `agent-service` cannot connect to Postgres, Neo4j, or Qdrant. |
