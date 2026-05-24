# Source Retraction Worker Runbook

## Purpose

Source retraction processing is split across two deterministic jobs:

- `jobs.source_retraction_job` scans pending `retracted` source lifecycle events and enqueues Neo4j outbox rows.
- `jobs.outbox_worker` drains those outbox rows and applies the Neo4j side effects.

## Commands

Run one source retraction pass:

```bash
python -m jobs.source_retraction_job
```

Run one source retraction pass with a smaller scan limit:

```bash
python -m jobs.source_retraction_job --limit 10
```

Expected source retraction CLI output:

```text
scanned_source_retraction_events=... enqueued_source_retraction_events=... failed_source_retraction_events=...
```

Run one outbox drain pass:

```bash
python -m jobs.outbox_worker
```

Legacy outbox CLI output must remain:

```text
processed_outbox_rows=... failed_outbox_rows=... scanned_outbox_rows=...
```

## Verification

Verify source retraction lifecycle processing:

```bash
pytest tests/unit/test_source_retraction_job.py -vv
pytest tests/integration/test_source_retraction_e2e_regression.py -vv
```

Verify outbox drain behavior:

```bash
pytest tests/unit/test_outbox_worker.py -vv
pytest tests/integration/test_outbox_eventual_consistency.py -vv
pytest tests/integration/test_outbox_neo4j_failure_retry_backoff.py -vv
pytest tests/integration/test_outbox_neo4j_side_effect.py -vv
pytest tests/integration/test_workflow_outbox_gate.py -vv
```

Full validation:

```bash
make validate
```
