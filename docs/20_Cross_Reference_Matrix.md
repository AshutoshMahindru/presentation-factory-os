# Cross-Reference Matrix

## Principle -> File -> Runtime Enforcement

| # | Principle | File | Runtime Enforcement |
|---|---|---|---|
| 1 | Replace policy with constraints | `04_Database_Schemas.sql`, `08_StateMachine_Spec.yaml` | SQL CHECK constraints, enum phases, state-machine transition guards |
| 2 | Separate deterministic orchestration from probabilistic generation | `01_Runtime_Architecture.md`, `11_Agent_SDK_Spec.md` | Workflow service owns transitions; agents use HTTP clients only |
| 3 | Financial truth must be formula-backed | `04_Database_Schemas.sql`, `09_Financial_Model_Schema.yaml` | `formula NOT NULL`, PK on financial cell identity, numeric assertion checker |
| 4 | Evidence must precede claims | `05_Evidence_Graph_Cypher.cypher`, `13_Source_Lifecycle_Spec.yaml` | Source match before claim create, `SUPPORTED_BY` edge required, retraction cascade |
| 5 | Provenance is mandatory | `04_Database_Schemas.sql`, `17_Observability_Spec.yaml` | Provenance table, traces table, model request logging, output hashes |
| 6 | Humans approve as a ledger, not boolean | `15_Human_Approval_Ledger.yaml`, `08_StateMachine_Spec.yaml` | Immutable approval entries, quorum computation, role-aware approval gates |
| 7 | Degradation is allowed but unsafe shipment is blocked | `12_Tool_Server_Degradation_Policy.yaml`, `21_DesignTokens.schema.json` | Fallback ladders with degraded status, materiality gates, and token schema validation |
| 8 | Routing and evaluation must be observable | `07_StandardContextPayload.schema.json`, `14_Rubric_Engine_Spec.yaml`, `17_Observability_Spec.yaml`, `30_Health_Endpoint_Surface.md` | Standard payload, routing log, rubric scores, alert thresholds, implemented health subresource endpoints |
| 9 | Audience psychology must be schema-first | `04_Database_Schemas.sql`, `22_AudienceProfile.schema.json`, `08_StateMachine_Spec.yaml`, `14_Rubric_Engine_Spec.yaml` | `audience_profile` JSONB object check, schema codegen, intake transition guard, blocking rubric cap |
| 10 | Narrative architecture must be deterministic without adding a phase | `06_SlideJobDefinition.schema.json`, `14_Rubric_Engine_Spec.yaml` | `narrative_arc` enum, deterministic `deck_builder/narrative_arc_validator.py`, structured objection-preemption map |
| 11 | Outbox preserves cross-store consistency | `04_Database_Schemas.sql`, `13_Source_Lifecycle_Spec.yaml`, `17_Observability_Spec.yaml` | Postgres outbox, idempotent job-runner writes, outbox lag alerts, transition blocking |
| 12 | Financial ingestion must be deterministic before LLM analysis | `23_Financial_Ingestion_Pipeline.yaml`, `11_Agent_SDK_Spec.md`, `09_Financial_Model_Schema.yaml` | Tool-server AST parser, parser provenance allow-list, direct Excel parsing banned in agents |
| 13 | Agent DB isolation is enforced by code and Docker networks | `16_Docker_Compose_Complete.yaml`, `01_Runtime_Architecture.md`, `11_Agent_SDK_Spec.md` | Agents have no DB imports, no DB credentials, and no Docker network route to data stores |

## File -> Service Mapping

| File | Consuming service(s) |
|---|---|
| `00_README_v3.2.4.md` | Human operators, onboarding |
| `01_Runtime_Architecture.md` | DevOps, workflow service, security review |
| `02_Repo_Structure.md` | Developers, CI |
| `03_Baby_Step_Command.md` | Developers |
| `04_Database_Schemas.sql` | Postgres, workflow service, observability, financial model |
| `05_Evidence_Graph_Cypher.cypher` | Neo4j, evidence graph service, lifecycle jobs |
| `06_SlideJobDefinition.schema.json` | Deck builder, narrative agent, visual agent, CI codegen, materiality export gate |
| `07_StandardContextPayload.schema.json` | Retrieval engine, Agent SDK, CI codegen |
| `08_StateMachine_Spec.yaml` | Workflow service, approval ledger, hard gates, tests |
| `09_Financial_Model_Schema.yaml` | Financial model service, slide numeric assertion validator |
| `10_Model_Proxy_Config.yaml` | LiteLLM proxy, agent service, rubric engine |
| `11_Agent_SDK_Spec.md` | Agents, CI DB-import guard |
| `12_Tool_Server_Degradation_Policy.yaml` | Tool server, deck builder, export gate |
| `13_Source_Lifecycle_Spec.yaml` | Job runner, evidence graph service, workflow service |
| `14_Rubric_Engine_Spec.yaml` | Rubric engine, workflow service, approval UI |
| `15_Human_Approval_Ledger.yaml` | Workflow service, approval API, UI |
| `16_Docker_Compose_Complete.yaml` | Docker runtime, local devops |
| `17_Observability_Spec.yaml` | Workflow service, retrieval engine, job runner, dashboards |
| `18_CI_CD_Schema_Validation.md` | GitHub Actions, Makefile, CI |
| `19_Implementation_Plan_v3.2.4.md` | Delivery management |
| `20_Cross_Reference_Matrix.md` | Architecture review, CI checklist, human audit |
| `21_DesignTokens.schema.json` | Design token validator, UI, deck builder, CI codegen |
| `22_AudienceProfile.schema.json` | Workflow service, rubric engine, CI codegen, intake guard |
| `23_Financial_Ingestion_Pipeline.yaml` | Tool-server, financial model validator, financial agent, CI YAML validation |
| `24_API_Examples.md` | API implementers, workflow-service, approval API, integration-test authors |
| `30_Health_Endpoint_Surface.md` | Workflow service, operators, integration-test authors |
| `31_API_Control_Plane_Contracts.md` | Workflow service, approval API, source lifecycle API, integration-test authors |

## Consistency Checklist

| Check | Required consistency | Status target |
|---|---|---|
| Phase names match DB constraints | `created`, `intake`, `strategy`, `research`, `financial_model`, `narrative`, `visual_design`, `review`, `approved`, `exported`, `rejected` appear consistently in SQL and YAML | Must pass |
| Model names match rubric judge entries | `qwen3-235b-a22b`, `qwen2.5-vl-7b`, `deepseek-r1-distill-32b` appear in proxy config and rubric engine | Must pass |
| Slide job enum referenced | Slide job types in `06_SlideJobDefinition.schema.json` are consumed by deck builder and narrative agent | Must pass |
| Tool degradation matches hard gates | Degraded visuals block export in both tool policy and state-machine hard gates | Must pass |
| Quorum rules match state machine | Approval rules in `08_StateMachine_Spec.yaml` match `15_Human_Approval_Ledger.yaml` | Must pass |
| All YAML parses | `08`, `09`, `10`, `12`, `13`, `14`, `15`, `17` parse with `yaml.safe_load` | Must pass |
| All JSON Schema validates | `06`, `07`, `21`, and `22` validate against Draft 2020-12 | Must pass |
| SQL validates | `04_Database_Schemas.sql` runs against PostgreSQL 16 | Must pass |
| SQL canonicalization matches deployable schema | `docs/04_Database_Schemas.sql` is canonical and `infra/postgres/init/001_schema.sql` matches byte-for-byte through `make validate-sql-canonical` | Must pass |
| Agent DB isolation | `agents/` imports no raw DB clients | Must pass |
| Source lifecycle blocks affected exports | Source retraction cascade affects claims, slides, projects, and exported-deck alerts | Must pass |
| Cypher validates | `05_Evidence_Graph_Cypher.cypher` executes against Neo4j 5 in CI | Must pass |
| Audience profile guard wired | `projects.audience_profile`, `22_AudienceProfile.schema.json`, and `audience_psychology_adequate` guard align | Must pass |
| Narrative arc validator wired | `06_SlideJobDefinition.schema.json` narrative arc enum matches `14_Rubric_Engine_Spec.yaml` validator rules | Must pass |
| Project health dashboard read-only | `17_Observability_Spec.yaml` health endpoint aggregates existing metrics and does not drive transitions directly | Must pass |
| Phase-name enum synchronization | SQL phase CHECK constraints, `08_StateMachine_Spec.yaml`, generated code enums, API validators, and UI labels are regenerated together | Must pass |
| Agent Docker isolation | `agent-service` attaches only to `pfos_agent_runtime` and has no route to Postgres, Neo4j, or Qdrant | Must pass |
| Financial table naming | SQL and YAML both use `financial_cells` as the canonical formula-backed financial table name | Must pass |
| Outbox retry/backoff integration | Tests simulate Neo4j failure, verify retry/backoff, and confirm eventual outbox processing before transitions unblock | Must pass |
| Approval quorum phase scope | Quorum is evaluated on phase-completion transitions and invalidated by retreat into upstream phases | Must pass |
| API examples remain valid | `24_API_Examples.md` payloads match project creation, transition, and approval endpoint contracts | Must pass |




## Additional Operational Consistency Checklist

| Check | Requirement | Status |
|---|---|---|
| Retraction SLA alignment | `13_Source_Lifecycle_Spec.yaml` `maximum_cascade_latency_seconds` and `17_Observability_Spec.yaml` `retraction_queue_stalled` threshold must match at 30 seconds | Must pass |
| Phase enum synchronization | Phase names must match across SQL CHECK constraints, `08_StateMachine_Spec.yaml`, generated code enums, API validators, and UI labels | Must pass |
| Test path consistency | Unit tests live under `tests/unit/`, integration tests under `tests/integration/`, load tests under `tests/load/` | Must pass |
| Agent network isolation | `tests/integration/test_agent_network_isolation.py` must prove agent container cannot connect to Postgres, Neo4j, or Qdrant | Must pass |
| Job-runner trust boundary | Job-runner may access data stores only as trusted deterministic infrastructure executing outbox/source lifecycle work; agent-service may not | Must pass |
| API media type versioning | API examples and contract tests must use `application/vnd.pfos.v3.2.4+json` | Must pass |
| Control-plane E2E coverage | Project lifecycle, review approval/export, and source retraction flows are covered by API/control-plane integration tests | Must pass |
