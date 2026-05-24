# Baby Step Execution Protocol

## Purpose

This protocol defines how PFOS implementation baby steps should be executed after Step 49.

The goal is to keep the speed benefits of structured execution while avoiding fragile YAML-driven code patching.

## Core rule

YAML plans are metadata and validation plans only.

Do not place large Python patch scripts, multiline source-code rewrites, or fragile string/regex replacements inside YAML command blocks.

## Preferred execution pattern

Each baby step should use:

1. A clean git branch.
2. Direct file replacement for new or substantially changed files.
3. Small, explicit Python patch scripts only when the anchor is stable and easy to inspect.
4. Focused tests before full validation.
5. Manual commit after validation passes.
6. Merge to main only after make validate passes.

## Allowed YAML usage

YAML baby-step plans may contain metadata only:

- step_id
- name
- branch
- objective
- commit_message
- validation_commands
- files_expected

## Disallowed YAML usage

Avoid YAML command blocks that contain large embedded source-code rewrites.

This pattern caused repeated failures because source files evolved and anchors drifted.

## Preferred code modification methods

For new files, use direct file creation with cat.

For substantially changed files, prefer full-file replacement when the file is small or medium sized.

For small edits, use short Python patch scripts with clear anchor checks.

## Validation rule

Every baby step must run:

- python -m compileall for changed Python packages
- focused pytest commands
- make validate

## Commit rule

Commit only after focused tests and full validation pass.

## Merge rule

Merge only after branch validation is green.

## Scope rule

Use medium baby steps:

- 2 to 5 files changed.
- 2 to 5 tests added or updated.
- One coherent subsystem slice.
- One branch.
- One commit.
- Validation green before merge.

## When to use the Baby Step Applier

The applier may still be used for simple file creation and validation-only plans.

Do not use it for large evolving-code patches unless the command block only calls a checked-in script or creates entirely new files.
