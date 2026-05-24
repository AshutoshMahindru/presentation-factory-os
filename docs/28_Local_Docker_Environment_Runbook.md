# Local Docker Environment Runbook

## Purpose

Use this runbook to operate the local Docker-backed PFOS environment with one
canonical Compose project and one canonical app compose file.

Canonical local settings:

```bash
export COMPOSE_PROJECT_NAME=pfos-dev
export COMPOSE_FILE=docker-compose.apps.yaml
```

The Makefile defaults to these values, so the `make` commands below are the
preferred operator interface.

## Start From Repo Root

```bash
cd presentation-factory-os
source .venv/bin/activate
git status --short --branch
```

## Docker Compose Status

Check the canonical PFOS app stack:

```bash
make docker-ps
```

Equivalent raw command:

```bash
docker compose -p pfos-dev -f docker-compose.apps.yaml ps
```

## Start The Stack

Start the canonical local app services:

```bash
make docker-up
```

Equivalent raw command:

```bash
docker compose -p pfos-dev -f docker-compose.apps.yaml up -d postgres neo4j qdrant workflow-service retrieval-engine tool-server agent-service
```

## Reset The PFOS Dev Stack

Use the Makefile reset when local state is stale or schema validation needs a
fresh Docker-backed environment:

```bash
make docker-reset-dev
```

This only targets the `pfos-dev` compose project. It does not run
`docker system prune`.

Equivalent raw command sequence:

```bash
docker compose -p pfos-dev -f docker-compose.apps.yaml down --remove-orphans --volumes
docker compose -p pfos-dev -f docker-compose.apps.yaml up -d postgres neo4j qdrant workflow-service retrieval-engine tool-server agent-service
make validate-sql-live
```

## Known Compose Project Mismatch

Older local runs may have created the fixed PFOS dev container names under a
different Compose project. This can make `docker compose ps` look empty even
when same-named containers exist, or it can cause name conflicts when starting
the canonical project.

Inspect PFOS dev containers before removing anything:

```bash
docker ps -a --filter name=pfos- --format '{{.Names}}\t{{.Status}}\t{{.Label "com.docker.compose.project"}}'
```

Prefer the canonical project reset:

```bash
make docker-reset-dev
```

If a one-time migration is required because old fixed-name PFOS containers are
owned by another Compose project, remove only those named PFOS dev containers:

```bash
docker rm -f pfos-postgres-dev pfos-neo4j-dev pfos-qdrant-dev pfos-workflow-service-dev pfos-retrieval-engine-dev pfos-tool-server-dev pfos-agent-service-dev
```

Then recreate the canonical stack and bootstrap Postgres:

```bash
make docker-up
make validate-sql-live
```

## Docker Doctor

Run the local environment doctor:

```bash
make docker-doctor
```

Equivalent raw command:

```bash
python scripts/check_docker_env.py --compose-project-name pfos-dev --compose-file docker-compose.apps.yaml
```

The doctor checks:

- `docker` command availability.
- `docker compose` availability.
- `docker-compose.apps.yaml` exists.
- Expected services are defined.
- Required Postgres tables exist when Postgres is reachable.

Required Postgres tables:

```text
projects
phase_transitions
approval_ledger
source_lifecycle_events
outbox
```

## Schema Bootstrap

Bootstrap or re-apply the checked-in Postgres schema:

```bash
make validate-sql-live
```

## Postgres Table Verification

Verify the required tables directly:

```bash
docker compose -p pfos-dev -f docker-compose.apps.yaml exec -T postgres psql -U pfos -d pfos -v ON_ERROR_STOP=1 -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('projects', 'phase_transitions', 'approval_ledger', 'source_lifecycle_events', 'outbox') ORDER BY table_name;"
```

## Source Lifecycle Queue Status

Inspect source lifecycle event queue status grouped by status and event type:

```bash
docker compose -p pfos-dev -f docker-compose.apps.yaml exec -T postgres psql -U pfos -d pfos -v ON_ERROR_STOP=1 -c "SELECT processing_status, event_type, count(*) AS event_count FROM source_lifecycle_events GROUP BY processing_status, event_type ORDER BY processing_status, event_type;"
```

Inspect pending source retractions:

```bash
docker compose -p pfos-dev -f docker-compose.apps.yaml exec -T postgres psql -U pfos -d pfos -v ON_ERROR_STOP=1 -c "SELECT id, project_id, source_id, created_at FROM source_lifecycle_events WHERE event_type = 'retracted' AND processing_status = 'pending' ORDER BY created_at ASC LIMIT 20;"
```

## Outbox Queue Status

Inspect outbox queue status grouped by processed flag, retry count, target store,
and operation type:

```bash
docker compose -p pfos-dev -f docker-compose.apps.yaml exec -T postgres psql -U pfos -d pfos -v ON_ERROR_STOP=1 -c "SELECT processed, error_count, target_store, operation_type, count(*) AS row_count FROM outbox GROUP BY processed, error_count, target_store, operation_type ORDER BY processed, error_count, target_store, operation_type;"
```

Inspect unprocessed outbox rows:

```bash
docker compose -p pfos-dev -f docker-compose.apps.yaml exec -T postgres psql -U pfos -d pfos -v ON_ERROR_STOP=1 -c "SELECT id, project_id, target_store, operation_type, error_count, created_at, last_error FROM outbox WHERE processed = FALSE ORDER BY created_at ASC LIMIT 20;"
```

## Source Retraction Job

Run one source retraction job pass:

```bash
python -m jobs.source_retraction_job
```

Run one source retraction job pass with a limit:

```bash
python -m jobs.source_retraction_job --limit 10
```

Expected source retraction CLI output:

```text
scanned_source_retraction_events=... enqueued_source_retraction_events=... failed_source_retraction_events=...
```

## Outbox Worker

Run one outbox worker pass:

```bash
python -m jobs.outbox_worker
```

Expected outbox worker CLI output:

```text
processed_outbox_rows=... failed_outbox_rows=... scanned_outbox_rows=...
```

## Focused Tests

Run source retraction focused tests:

```bash
pytest tests/unit/test_source_retraction_job.py -vv
```

Run outbox worker focused tests:

```bash
pytest tests/unit/test_outbox_worker.py -vv
```

Run Docker doctor unit tests:

```bash
pytest tests/unit/test_check_docker_env.py -vv
```

## Full Validation

Run full repository validation:

```bash
make validate
```

Run validation with canonical Docker startup, schema bootstrap, and doctor:

```bash
make validate-live
```
