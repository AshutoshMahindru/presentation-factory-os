# Codex Task 00 — Validation-Only Repository Check

## Context

We are transitioning PFOS v3.2.4 implementation to a Codex-assisted workflow.

Follow:

- `CODEX.md`
- `docs/25_Baby_Step_Execution_Protocol.md`

## Task

Run a validation-only repository check.

## Instructions

1. Start from current `main`.
2. Run `git status`.
3. Run focused smoke checks if needed.
4. Run `make validate`.
5. Do not modify files unless validation fails.
6. If validation fails, fix only the minimum compatibility issue required.
7. Do not merge to main.
8. If changes are required, create a branch and propose/open a PR.

## Acceptance criteria

- `make validate` passes.
- No unrelated code changes.
- No architecture changes.
- No merge to main.

## Required final response

Return:

1. Validation result.
2. Tests run.
3. Any files changed.
4. If files changed, provide branch/PR details.
