# Runtime Architecture

## Service graph

```text
+----------+      +------------------+      +---------------+
| Human UI | ---> | Workflow Service | ---> | Agent Service |
+----------+      +------------------+      +---------------+
       |                    |                       |
       |                    v                       v
       |            +------------------+     +-------------+
       |            | Approval Ledger  |     | LLM Proxy   |
       |            +------------------+     | LiteLLM     |
       |                    |                 +-------------+
       v                    v                       |
+----------------+   +------------------+           v
| Deck Preview   |   | Retrieval Engine | ---> +-------------+
+----------------+   +------------------+      | Local vLLM  |
                              |                | Remote APIs |
                              v                +-------------+
                    +-------------------------+
                    | Data Layer              |
                    | Neo4j / Postgres /      |
                    | Qdrant                  |
                    +-------------------------+
                              |
                              v
                       +-------------+
                       | Tool Server |
                       +-------------+
                              |
                              v
                       +-------------+
                       | Deck Builder|
                       +-------------+
                              |
                              v
                       +-------------+
                       | Export      |
                       +-------------+
```

## Network contracts

| Service | Port | Depends On | Never Talks To |
|---|---:|---|---|
| `ui` | 3000 | `workflow-service` | Postgres, Neo4j, Qdrant, LiteLLM directly |
| `workflow-service` | 8000 | Postgres, Neo4j, LiteLLM, `retrieval-engine`, `tool-server` | Qdrant directly except through retrieval facade |
| `agent-service` | internal | `retrieval-engine:8002`, `tool-server:8003`, `litellm-proxy:4000`, `workflow-service:8000` | Postgres, Neo4j, Qdrant |
| `retrieval-engine` | 8002 | Postgres, Neo4j, Qdrant | Deck export, UI write endpoints |
| `tool-server` | 8003 | Postgres for provenance, output volume | Raw agent credentials, UI browser state |
| `deck-builder` | internal | Tool outputs, Postgres metadata, slide schemas | Neo4j direct writes |
| `job-runner` | internal | Workflow service, source lifecycle, Postgres, Neo4j | Human UI session state |
| `litellm-proxy` | 4000 | Local vLLM endpoints, remote model APIs | Data stores directly |
| `postgres` | 5432 | named volume | External internet |
| `neo4j` | 7474/7687 | named volume, APOC | External internet |
| `qdrant` | 6333 | named volume | External internet |


## Docker network isolation

`agent-service` is attached only to `pfos_agent_runtime`, an internal bridge network shared with `workflow-service`, `retrieval-engine`, `tool-server`, and `litellm-proxy`. Postgres, Neo4j, and Qdrant are attached only to `pfos_data` and are not reachable from `pfos_agent_runtime`. This makes the Agent SDK database ban enforceable at the infrastructure layer: even if an agent imports a raw database client, it has no routable Docker network path to the data stores.

| Network | Attached services | Purpose | Agent access |
|---|---|---|---|
| `pfos_data` | Postgres, Neo4j, Qdrant, workflow-service, retrieval-engine, tool-server, litellm-proxy, job-runner | Data-store and trusted deterministic-service network | No |
| `pfos_service` | UI, workflow-service, retrieval-engine, tool-server, litellm-proxy, job-runner | Application/service plane | No direct agent attachment |
| `pfos_agent_runtime` | agent-service, workflow-service, retrieval-engine, tool-server, litellm-proxy | Narrow HTTP-only agent runtime network | Yes |


## Job-runner trust boundary

`job-runner` is trusted deterministic infrastructure, not an agent. It may connect to Postgres and Neo4j because it executes idempotent, schema-governed side effects from the Postgres outbox and source lifecycle queues. It does not generate narrative content, does not call LLMs for phase advancement, and does not accept arbitrary agent instructions. By contrast, `agent-service` is probabilistic generation runtime and is intentionally isolated from data stores at both code and Docker-network levels.

## Data sovereignty rule

Evidence graph and project state are local-first. Postgres, Neo4j, and Qdrant are authoritative local stores. Remote models may receive bounded, redacted context through LiteLLM only when routing rules require fallback due to insufficient local VRAM, excessive queue depth, or unavailable local models. Remote model calls must log request metadata and provenance, but never persist raw model responses if `log_responses` is false.

## Deterministic versus probabilistic boundary

The workflow service, state machine, validators, approval ledger, and export gates are deterministic. LLMs may draft, critique, summarize, classify, and suggest. LLM output cannot advance a phase, validate a formula, create an unsupported claim, approve a deck, or export a deck without deterministic validation.

## Cross-Store Consistency Contract

The workflow-service must not directly write Neo4j for cross-cutting operations such as source retractions, claim-support changes, or retreat side effects. It writes the authoritative event and an `outbox` row in the same Postgres transaction. The job-runner polls the outbox, performs idempotent Neo4j writes in batches, and marks the outbox item processed. Phase transitions and export are blocked while a project has failed or unprocessed outbox items.
