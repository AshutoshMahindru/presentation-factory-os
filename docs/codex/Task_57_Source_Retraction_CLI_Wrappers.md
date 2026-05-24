# Codex Task 57 — Source Retraction CLI Wrappers and Runbook

## Context

We are implementing PFOS v3.2.4.

Current status:

- Main branch should be green.
- Baby Steps 1–56 are complete.
- Step 49 established the execution protocol.
- YAML baby-step files are metadata only.
- Use direct file replacement or small explicit patches.
- Preserve all existing integration behavior.
- Do not merge to main.

Follow:

- CODEX.md
- docs/25_Baby_Step_Execution_Protocol.md

## Task

Baby Step 57 — Add CLI wrappers and runbook coverage for source retraction and outbox workers.

## Objective

Add safe, deterministic CLI entrypoints or documented commands for:

1. Running the source retraction job.
2. Running the outbox worker.
3. Verifying source retraction lifecycle processing.
4. Verifying outbox drain behavior.

## Acceptance criteria

1. Source retraction job can be invoked from CLI or module form.
2. Outbox worker CLI behavior remains backward compatible:
   processed_outbox_rows=... failed_outbox_rows=... scanned_outbox_rows=...
3. A metadata-only baby-step YAML file is created.
4. Focused tests are added or updated.
5. Existing outbox integration tests continue to pass.
6. make validate passes.
7. No merge to main.

## Likely files

- jobs/source_retraction_job.py
- jobs/outbox_worker.py
- docs/
- tests/unit/test_source_retraction_job.py
- tests/unit/test_outbox_worker.py
- .pfos/baby_steps/057_source_retraction_cli_wrappers.yaml

## Compatibility contracts to preserve

- outbox worker CLI output:
  processed_outbox_rows=... failed_outbox_rows=... scanned_outbox_rows=...
- claim_updated outbox behavior
- Neo4j Project MERGE using:
  (:Project {id: ...})
- retry ceiling using:
  LEAST(error_count + 1, 5)
- workflow outbox gate drain behavior
- hard-gate bundle semantics for no_blocking_rules

## Required tests

Run at minimum:

- python -m compileall system jobs api
- pytest tests/unit/test_source_retraction_job.py -vv
- pytest tests/unit/test_outbox_worker.py -vv
- pytest tests/integration/test_outbox_eventual_consistency.py -vv
- pytest tests/integration/test_outbox_neo4j_failure_retry_backoff.py -vv
- pytest tests/integration/test_outbox_neo4j_side_effect.py -vv
- pytest tests/integration/test_workflow_outbox_gate.py -vv
- make validate

## Required final response from Codex

Return:

1. Summary of changes.
2. Files changed.
3. Tests run.
4. Whether make validate passed.
5. Branch or PR details.
6. Any risks.
