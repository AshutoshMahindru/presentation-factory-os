# Codex Baby Step Task Template

## Context

We are implementing PFOS v3.2.4.

Current status:

- Main branch is green.
- Previous baby steps are complete through the latest merged step.
- Follow `CODEX.md`.
- Follow `docs/25_Baby_Step_Execution_Protocol.md`.
- YAML baby-step files are metadata only.
- Do not put large code patch scripts inside YAML.
- Use direct file replacement or small explicit patches.
- Preserve all existing integration tests.
- Run focused tests first.
- Run `make validate`.
- Do not merge to main.

## Task

Baby Step `<NUMBER>` — `<NAME>`

Objective:

`<OBJECTIVE>`

## Acceptance criteria

1. `<CRITERION 1>`
2. `<CRITERION 2>`
3. `<CRITERION 3>`
4. Existing tests remain green.
5. `make validate` passes.

## Likely files

- `<file 1>`
- `<file 2>`
- `<test file 1>`
- `.pfos/baby_steps/<step_file>.yaml`

## Constraints

Preserve these compatibility contracts:

- outbox worker CLI output:
  `processed_outbox_rows=... failed_outbox_rows=... scanned_outbox_rows=...`
- `claim_updated` outbox behavior
- Neo4j Project MERGE using:
  `(:Project {id: ...})`
- retry ceiling using:
  `LEAST(error_count + 1, 5)`
- workflow outbox gate drain behavior
- hard-gate bundle semantics for `no_blocking_rules`

## Required final response from Codex

Return:

1. Summary of files changed.
2. Tests run.
3. Whether `make validate` passed.
4. Any risks or follow-up recommendations.
5. PR/branch details.
