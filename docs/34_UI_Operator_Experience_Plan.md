# UI Operator Experience Plan

Baby Step 78 adds the first typed UI API client surface for implemented
workflow-service control-plane endpoints. It is a UI-only hardening step and
does not change API behavior, Docker, jobs, source lifecycle processing, outbox
worker behavior, or deck/export behavior.

## Client Contract

`ui/lib/api.ts` exposes `createPfosApiClient` with v3.2.4 media-type headers and
typed helpers for the implemented control-plane endpoints:

| UI helper | API endpoint |
| --- | --- |
| `getServiceHealth` | `GET /health` |
| `getServiceReadiness` | `GET /ready` |
| `getProjectOutboxStatus` | `GET /health/projects/{project_id}/outbox` |
| `getProjectSourceRetractionStatus` | `GET /health/projects/{project_id}/source-retractions` |
| `getProjectHardGateStatus` | `GET /health/projects/{project_id}/hard-gates` |
| `getProjectControlPlaneHealth` | Fan-out across the implemented project outbox, source-retraction, and hard-gate status endpoints |
| `getApprovalStatus` | `GET /projects/{project_id}/approvals/status/{phase}` |
| `requestPhaseTransition` | `POST /projects/{project_id}/phase-transitions` |

The client preserves non-2xx response payloads in `ApiClientError.payload` so
operator UI screens can show deterministic API errors such as
`project_not_found`, `phase_mismatch`, or `transition_blocked` without inventing
new error semantics.

## Deferred Surfaces

`GET /health/projects/{project_id}` remains planned in the API documentation and
is not called by the Step 78 client. Dashboard work should continue using
`getProjectControlPlaneHealth` until the aggregate project health endpoint has
an implemented score, evidence coverage, open retraction, days-in-phase,
approval velocity, and blocking-gate contract.

No export-readiness API helper is added in this step. `api/exports.py` is still
an empty placeholder, and the UI client should not introduce a synthetic export
readiness contract before the deck/export API surface exists.

## Follow-On UI Steps

- Step 79 adds a presentational project dashboard component backed by
  `getProjectControlPlaneHealth` types. It surfaces outbox queue state, source
  retraction queue state, hard-gate status, and an optional approval snapshot
  without adding API behavior.
- Step 80 adds the operator-facing approval UI from `getApprovalStatus`. It
  renders the current approval ledger snapshot, quorum state, missing roles,
  decision counts, and escalation state without adding approval submission or
  changing backend behavior.
- Step 81 adds read-only hard-gate and queue status panels for operator
  visibility. `QueueStatusPanel` surfaces pending and failed outbox status,
  pending source retraction cascades, and failed or blocked source lifecycle
  events when those row details are present in an existing API payload. With the
  current status endpoints it falls back to deterministic count rows rather than
  inventing a backend contract. `HardGateStatusPanel` shows pass, fail, and
  blocked gate state, failed check reasons, check metadata, and the existing
  stale artifact warning message for `stale_due_to_retreat` blockers.
- Step 82 adds a read-only export readiness panel that composes the existing
  project control-plane health data with optional deck/export metadata already
  available to a UI screen. It does not add a new export endpoint or client
  helper, and it labels unexposed source appendix, evidence-map, or financial
  reference data as unknown instead of treating the project as export-ready.

## Step 80 Approval UI

`ui/app/approvals/page.tsx` provides a read-only operator page for inspecting a
project approval phase. Operators enter a project ID, select the phase, and load
the existing `GET /projects/{project_id}/approvals/status/{phase}` contract via
the Step 78 API client.

`ui/components/ApprovalLedger.tsx` is the reusable presentation component for
that response. It shows:

- quorum status and decision rule
- required approvals and counted decision entries
- approvals, rejections, abstentions, and changes-requested counts
- missing roles from the quorum evaluator
- escalation status, escalation reason, and blocking rejection state
- explicit empty, loading, and error states

The current API returns a phase-scoped approval status snapshot rather than
actor-level approval rows. Step 80 therefore presents the ledger as decision
summary rows and leaves approval submission, actor-level browsing, and export
readiness UI for later steps with promoted API contracts.

## Export Readiness UI

`ui/components/ExportReadinessPanel.tsx` is a presentational component for
operator-facing export checks. The component accepts:

| Prop | Source |
| --- | --- |
| `health` | Existing `getProjectControlPlaneHealth` fan-out over outbox, source-retraction, and hard-gate endpoints |
| `deck` | Optional deck snapshot already held by the surrounding UI |
| `exportMetadata` | Optional source appendix, evidence-map, and financial reference metadata already held by the surrounding UI |

The panel surfaces blocking export conditions without mutating backend state or
weakening the deterministic export gate:

- Failed or unprocessed outbox rows block export readiness.
- Open source retraction cascade work blocks export readiness.
- Failed hard-gate checks are listed as blockers, including stale downstream
  artifacts when the current hard-gate payload exposes them.
- Degraded visuals on high or medium materiality slides block readiness when
  slide data is exposed.
- Low materiality degraded visuals are shown as warnings.
- High or medium materiality slides without evidence references block readiness
  when slide data is exposed.
- Source appendix and evidence-map metadata are checked when exposed; otherwise
  the section is marked unknown.
- Financial validation, unsupported financial claims, missing financial cells,
  and unvalidated financial references block readiness when exposed.

The overall headline is intentionally conservative:

- `Export blocked` appears when any exposed blocker is present.
- `Export ready` appears only when all exposed sections are ready and no section
  is unknown.
- `No exposed export blockers` appears when there are no blockers but one or
  more readiness inputs are unavailable.

This keeps the display read-only and avoids creating a fake export success path
while still giving operators a concise blocker list.
