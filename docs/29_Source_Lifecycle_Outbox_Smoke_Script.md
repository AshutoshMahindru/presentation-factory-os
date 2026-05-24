# Source Lifecycle and Outbox Smoke Script

## Purpose

`scripts/source_lifecycle_outbox_smoke.py` prints a concise, read-only
operational report for the PFOS source lifecycle queue and Postgres outbox. It
is intended for local operator checks after schema bootstrap, worker changes, or
queue-drain debugging.

The script only executes `SELECT` statements. It does not mutate
`source_lifecycle_events`, does not mutate `outbox`, does not change schema, and
does not run `jobs.source_retraction_job` or `jobs.outbox_worker`.

## Database URL Resolution

Pass the database URL explicitly:

```bash
python scripts/source_lifecycle_outbox_smoke.py --database-url postgresql://pfos:pfos@localhost:5432/pfos
```

Run through the repository Makefile target:

```bash
DATABASE_URL=postgresql://pfos:pfos@localhost:5432/pfos make smoke-source-lifecycle-outbox
```

The Makefile target uses the repository `PYTHON` variable, which defaults to
`python3`.

If `--database-url` is omitted, the script checks environment variables in this
order:

```text
DATABASE_URL
POSTGRES_URL
```

The script exits non-zero when no database URL is available.

## Required Tables

The smoke report verifies these required public tables:

```text
projects
source_lifecycle_events
outbox
```

The script exits non-zero when any required table is missing. When required
tables are missing, it reports table presence and stops before querying queue
tables.

## Report Contents

The report includes:

- required table presence
- `source_lifecycle_events` grouped by `processing_status` and `event_type`
- `outbox` grouped by `processed`, `error_count`, `target_store`, and
  `operation_type`
- oldest pending or failed `source_lifecycle_events` row, if one exists
- oldest unprocessed or failed `outbox` row, if one exists

Example:

```text
PFOS Source Lifecycle and Outbox Smoke Report

Required tables:
  projects: present
  source_lifecycle_events: present
  outbox: present

Source lifecycle events by processing_status and event_type:
  processing_status=pending event_type=retracted row_count=2

Outbox by processed, error_count, target_store, and operation_type:
  processed=false error_count=1 target_store=neo4j operation_type=source_retracted row_count=1

Oldest pending or failed source_lifecycle_events row:
  id=... project_id=... source_id=... event_type=retracted processing_status=pending error_count=0 created_at=... last_error=null

Oldest unprocessed or failed outbox row:
  id=... project_id=... target_store=neo4j operation_type=source_retracted processed=false error_count=1 created_at=... last_error=...

Smoke status: PASS required tables present
```

## Validation

Run the focused checks:

```bash
python -m compileall scripts
pytest tests/unit/test_source_lifecycle_outbox_smoke.py -vv
```

Run full repository validation:

```bash
make validate
```
