# Outbox and Source Lifecycle Operational Status Runbook

## Purpose

Use this runbook to validate the local Docker-backed PFOS environment after
source lifecycle and outbox worker changes. It covers compose status, Postgres
schema bootstrap, queue inspection, worker invocation, and validation commands.

## Start From Repo Root

```bash
cd presentation-factory-os
source .venv/bin/activate
```

Confirm the expected Python and repository context:

```bash
python --version
git status --short --branch
```

## Docker Compose Status

Check whether the PFOS app services are attached to the current compose project:

```bash
docker compose -f docker-compose.apps.yaml ps
```

If services are missing from this output but same-named PFOS dev containers
exist, the local Docker daemon may have containers from another compose project.
This can happen because the app compose file uses fixed `container_name` values.

Inspect same-named PFOS containers:

```bash
docker ps -a --filter name=pfos- --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
```

## Targeted PFOS Dev Container Cleanup

Only use this targeted cleanup for local PFOS dev containers when compose status
shows the current checkout cannot see or recreate them:

```bash
docker rm -f pfos-postgres-dev pfos-neo4j-dev pfos-qdrant-dev pfos-workflow-service-dev pfos-retrieval-engine-dev pfos-tool-server-dev pfos-agent-service-dev
```

Start the documented app stack:

```bash
docker compose -f docker-compose.apps.yaml up -d postgres neo4j qdrant workflow-service retrieval-engine tool-server agent-service
```

Bootstrap a fresh Postgres container with the checked-in schema:

```bash
make validate-sql-live
```

Run full validation after the stack and schema are ready:

```bash
make validate
```

## Postgres Table Verification

Verify the required Postgres tables exist:

```bash
docker compose -f docker-compose.apps.yaml exec -T postgres psql -U pfos -d pfos -v ON_ERROR_STOP=1 -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('projects', 'source_lifecycle_events', 'outbox') ORDER BY table_name;"
```

Expected table names:

```text
outbox
projects
source_lifecycle_events
```

## Source Lifecycle Queue Status

Inspect source lifecycle event queue status grouped by status and event type:

```bash
docker compose -f docker-compose.apps.yaml exec -T postgres psql -U pfos -d pfos -v ON_ERROR_STOP=1 -c "SELECT processing_status, event_type, count(*) AS event_count FROM source_lifecycle_events GROUP BY processing_status, event_type ORDER BY processing_status, event_type;"
```

Inspect pending source retractions only:

```bash
docker compose -f docker-compose.apps.yaml exec -T postgres psql -U pfos -d pfos -v ON_ERROR_STOP=1 -c "SELECT id, project_id, source_id, created_at FROM source_lifecycle_events WHERE event_type = 'retracted' AND processing_status = 'pending' ORDER BY created_at ASC LIMIT 20;"
```

## Outbox Queue Status

Inspect outbox queue status grouped by processed flag, retry count, target store,
and operation type:

```bash
docker compose -f docker-compose.apps.yaml exec -T postgres psql -U pfos -d pfos -v ON_ERROR_STOP=1 -c "SELECT processed, error_count, target_store, operation_type, count(*) AS row_count FROM outbox GROUP BY processed, error_count, target_store, operation_type ORDER BY processed, error_count, target_store, operation_type;"
```

Inspect unprocessed outbox rows only:

```bash
docker compose -f docker-compose.apps.yaml exec -T postgres psql -U pfos -d pfos -v ON_ERROR_STOP=1 -c "SELECT id, project_id, target_store, operation_type, error_count, created_at, last_error FROM outbox WHERE processed = FALSE ORDER BY created_at ASC LIMIT 20;"
```

## Source Retraction Job Invocation

Run one source retraction job pass:

```bash
python -m jobs.source_retraction_job
```

Run one source retraction job pass with a smaller scan limit:

```bash
python -m jobs.source_retraction_job --limit 10
```

Expected source retraction CLI output is one line:

```text
scanned_source_retraction_events=... enqueued_source_retraction_events=... failed_source_retraction_events=...
```

## Outbox Worker Invocation

Run one outbox worker pass:

```bash
python -m jobs.outbox_worker
```

Expected outbox worker CLI output is one line:

```text
processed_outbox_rows=... failed_outbox_rows=... scanned_outbox_rows=...
```

## Focused Tests

Run source retraction job focused tests:

```bash
pytest tests/unit/test_source_retraction_job.py -vv
```

Run outbox worker focused tests:

```bash
pytest tests/unit/test_outbox_worker.py -vv
```

## Full Validation

Run full repository validation:

```bash
make validate
```
