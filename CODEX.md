# PFOS Codex Instructions

## Project status

PFOS v3.2.4 is implemented through the latest merged baby step on main.

Before making changes:

1. Run `git status`.
2. Inspect relevant files.
3. Run focused tests for the target subsystem.
4. Preserve all existing tests.
5. Run `make validate` before reporting completion.

## Execution protocol

Follow `docs/25_Baby_Step_Execution_Protocol.md`.

YAML baby-step files are metadata only.

Do not place large source-code patches inside YAML command blocks.

Prefer:

- direct file replacement for small or medium files
- small explicit patches with stable anchors
- focused tests before full validation

## Safety rules

Do not merge to main.

Do not change unrelated architecture.

Do not remove legacy integration behavior unless explicitly asked.

Do not mark work complete unless `make validate` passes.

## Current compatibility contracts

Preserve:

- outbox worker CLI output:
  `processed_outbox_rows=... failed_outbox_rows=... scanned_outbox_rows=...`
- `claim_updated` outbox behavior
- Neo4j Project MERGE using:
  `(:Project {id: ...})`
- retry ceiling using:
  `LEAST(error_count + 1, 5)`
- workflow outbox gate drain behavior
- hard-gate bundle semantics for `no_blocking_rules`

## Baby-step workflow

For each new baby step:

1. Create a branch from main.
2. Create a metadata-only `.pfos/baby_steps/<step>.yaml`.
3. Modify code using direct file replacement or small explicit patches.
4. Add focused tests.
5. Run focused tests.
6. Run `make validate`.
7. Commit only after validation passes.
8. Push branch and open/propose PR.
9. Do not merge.
