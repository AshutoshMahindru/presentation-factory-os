# Outbox Worker Neo4j Driver

Baby Step 93 replaces the legacy `docker compose exec ... cypher-shell` path in
`jobs.outbox_worker` with the official Neo4j Python driver.

The outbox worker remains deterministic infrastructure. This exception does not
change the agent database import ban: `agents/` still must not import database
drivers or connect to Postgres, Neo4j, Qdrant, Redis, MongoDB, or similar data
stores.

## Runtime Configuration

The worker reads Neo4j connection settings from environment variables:

- `NEO4J_URI`, default `bolt://localhost:7687`
- `NEO4J_USER`, default `neo4j`
- `NEO4J_PASSWORD`, default `pfos_neo4j_password`
- `NEO4J_AUTH`, optional `user/password` fallback when `NEO4J_PASSWORD` is not set
- `NEO4J_DATABASE`, optional database name

When the worker runs inside a service container on the PFOS data network, set:

```bash
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=pfos_neo4j_password
```

When running the worker directly from the host, the configured `NEO4J_URI` must
point at a Bolt endpoint reachable from the host process, such as a Neo4j service
with port `7687` published.

## Compatibility

The CLI contract is unchanged:

```bash
python -m jobs.outbox_worker
```

prints one line:

```text
processed_outbox_rows=... failed_outbox_rows=... scanned_outbox_rows=...
```

The worker still marks rows processed only after the handler completes
successfully. Handler failures are still recorded through
`OutboxRepository.mark_failed`, preserving existing `error_count` and retry
ceiling behavior.

Project side effects remain idempotent via:

```cypher
MERGE (p:Project {id: $project_id})
```

with parameterized updates for `name` and `current_phase`.
