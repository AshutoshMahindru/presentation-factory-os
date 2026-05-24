# UI Operator Smoke Path

Baby Step 83 defines a lightweight operator smoke path for the UI surfaces
introduced across the UI sequence. It does not change backend API behavior,
Docker, jobs, source lifecycle processing, outbox worker behavior, database
schema, or deck/export behavior.

## Scope

The smoke path proves that an operator can discover the project status surfaces
needed to decide whether a project is ready to advance:

1. Open the project dashboard for a known project.
2. Review project health and overall blocked/ready state.
3. Inspect hard-gate results and queue status.
4. Inspect approval and quorum status for the active phase.
5. Inspect export readiness before attempting delivery.

This step intentionally keeps coverage static because the repository does not
configure a UI test runner. The root `package.json` has no npm scripts, and
there is no Next, Vite, Jest, Vitest, or Playwright configuration to extend.

## Operator Path

| Step | Operator action | Expected UI evidence | Backing contract |
| --- | --- | --- | --- |
| 1 | Open the project dashboard for `{project_id}`. | The dashboard identifies the project and active phase. | `ui/components/ProjectHealth.tsx` receives `projectId`, optional `phase`, and `ProjectControlPlaneHealth`. |
| 2 | Review project health. | The dashboard shows a ready/blocked status and summary counts for operational blockers. | `createPfosApiClient().getProjectControlPlaneHealth(projectId)` fans out to implemented status endpoints. |
| 3 | Inspect hard gates and queues. | The dashboard renders queue status, hard-gate checks, failed outbox count, and source-retraction queue counts. | `GET /health/projects/{project_id}/outbox`, `GET /health/projects/{project_id}/source-retractions`, and `GET /health/projects/{project_id}/hard-gates`. |
| 4 | Inspect approval and quorum status. | The dashboard can render an approval snapshot, and `/approvals` renders the approval ledger query page. | `GET /projects/{project_id}/approvals/status/{phase}`. |
| 5 | Inspect export readiness. | `ExportReadinessPanel` renders blockers, warnings, unknown inputs, visual readiness, source appendix readiness, financial reference readiness, and stale artifact readiness. | Export readiness uses supplied project health, deck, and export metadata inputs without synthesizing fake readiness data. |

## Smoke Coverage

`tests/unit/test_ui_operator_smoke_path.py` provides the focused smoke coverage
for this step:

- Confirms this runbook documents the five operator actions.
- Confirms the typed API client exposes the project health, queue, hard-gate,
  approval, and transition helpers used by the operator path.
- Confirms `ProjectHealth`, `QueueStatusPanel`, `HardGateStatusPanel`,
  `ApprovalLedger`, `/approvals`, and `ExportReadinessPanel` expose renderable
  labels for the operator path.
- Confirms no npm UI test/lint script is assumed while `package.json` remains
  empty.
- Confirms the checked UI components do not introduce obvious mock/fake data
  markers.

## Current Base Note

This branch is rebased onto `origin/main` with Steps 80-82 present. The
available UI surface includes `ui/app/approvals/page.tsx` plus the project
health, queue status, hard-gate status, approval ledger, and export readiness
components.

There is still no configured UI test runner. If a UI framework is added later,
this smoke path should be promoted to a render or navigation test using that
existing framework rather than introducing a new one here.
