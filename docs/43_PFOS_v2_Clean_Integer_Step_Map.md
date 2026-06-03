# PFOS v2 Clean Integer Step Map

This document is the canonical repo map for applying the PFOS v2.0 plan after
the existing v3.2.4 hardening work. The v2 source files contain decimal chat
steps (`124.5`, `124.6`); this repo uses the clean integer sequence requested by
the operator.

## Normalization

| v2 source label | Clean step | Name |
| --- | ---: | --- |
| 124.5 | 123 | Chat Session Schema + API Surface |
| 124.6 | 124 | Intake Chat Orchestrator |
| 124 | 125 | CI Workflow and SQL Canonicalization |
| 125-163 | 126-164 | Shifted forward by one integer |

Older `.pfos/baby_steps` files below Step 123 are retained as historical
implementation metadata. Clean v2 execution starts at Step 123 and ends at
Step 164.

## Wave Ownership

| Wave | Clean steps | Owner lane |
| --- | --- | --- |
| 0 | 123-164 metadata | Realignment and control-plane mapping |
| 1A | 123-129 | Chat, audience, intake, persona guard |
| 1B | 130-137 | Source memory, retrieval, thesis, deep-read |
| 1C | 138-142 | Financial sandbox, compiler, review, stress, promotion |
| 2D | 143-146 | Slide factory and export metadata |
| 2E | 147-150 | E2E, retraction cascade, UI dashboard, load hardening |
| 3F | 151-153 | DLS, token autogeneration, corpus ingestion |
| 3G | 154-156 | Layout solver, vector charts, diagram/table vectors |
| 3H | 157-159 | Headless rendering, visual QA, vision judge |
| 3I | 160-164 | Slide master, assets, multi-format export, regression, overrides |

## Already Implemented Or Partially Implemented

- Step 123 chat schema/API: implemented through `system/chat_repository.py`,
  workflow intake-chat endpoints, and chat integration tests.
- Step 124 intake orchestrator: implemented through
  `agents/intake_chat_orchestrator.py` and intake-flow tests.
- Step 125 CI/SQL canonicalization: SQL canonicalization is implemented;
  GitHub Actions workflow parity still requires confirmation because this
  checkout has no `.github/workflows` directory.
- Step 141 stress/convergence guard: deterministic stress engine and
  `model_validated` guard coverage exist.
- Step 142 sandbox promotion: implemented through sandbox-to-canonical
  financial cell promotion with `promoted_from_spec` lineage.

## Implementation Rule

Agents must use the clean step numbers in `.pfos/baby_steps/123_*.yaml` through
`.pfos/baby_steps/164_*.yaml`. If an implementation was previously committed
under a different repo-era step number, do not reimplement it; add or update
tests/docs only where needed to close the clean v2 contract.
