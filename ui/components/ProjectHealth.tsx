import type {
  ApprovalStatus,
  PfosPhase,
  ProjectControlPlaneHealth,
} from "../lib/api";

export interface ProjectHealthProps {
  projectId: string;
  phase?: PfosPhase | string;
  health: ProjectControlPlaneHealth;
  approvalStatus?: ApprovalStatus | null;
  isLoading?: boolean;
  errorMessage?: string | null;
  onRefresh?: () => void;
  onRequestPhaseTransition?: () => void;
}

interface HealthSummaryItem {
  label: string;
  value: string | number;
  status: "clear" | "attention";
  detail: string;
}

function formatAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) {
    return "No open age";
  }

  if (seconds < 60) {
    return `${seconds}s open`;
  }

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m open`;
  }

  const hours = Math.floor(minutes / 60);
  return `${hours}h open`;
}

function statusLabel(blocked: boolean): string {
  return blocked ? "Attention" : "Clear";
}

function statusClass(status: "clear" | "attention"): string {
  return `pfos-status pfos-status-${status}`;
}

function buildSummaryItems(health: ProjectControlPlaneHealth): HealthSummaryItem[] {
  const retractionOpenCount =
    health.sourceRetractions.pending_count +
    health.sourceRetractions.processing_count +
    health.sourceRetractions.failed_count;

  return [
    {
      label: "Outbox",
      value: health.outbox.unprocessed_count + health.outbox.failed_count,
      status: health.outbox.blocked ? "attention" : "clear",
      detail: `${health.outbox.failed_count} failed, ${formatAge(
        health.outbox.oldest_unprocessed_age_seconds,
      )}`,
    },
    {
      label: "Retractions",
      value: retractionOpenCount,
      status: health.sourceRetractions.blocked ? "attention" : "clear",
      detail: `${health.sourceRetractions.failed_count} failed, ${formatAge(
        health.sourceRetractions.oldest_open_age_seconds,
      )}`,
    },
    {
      label: "Hard gates",
      value: health.hardGates.failed_checks.length,
      status: health.hardGates.passed ? "clear" : "attention",
      detail: `${health.hardGates.checks.length} checks evaluated`,
    },
  ];
}

export function ProjectHealth({
  projectId,
  phase,
  health,
  approvalStatus,
  isLoading = false,
  errorMessage = null,
  onRefresh,
  onRequestPhaseTransition,
}: ProjectHealthProps) {
  const summaryItems = buildSummaryItems(health);
  const dashboardBlocked = summaryItems.some((item) => item.status === "attention");

  return (
    <section
      className="pfos-project-health"
      aria-labelledby="project-health-heading"
      aria-busy={isLoading}
    >
      <header className="pfos-project-health-header">
        <div>
          <p className="pfos-kicker">Project dashboard</p>
          <h2 id="project-health-heading">Control-plane status</h2>
          <p className="pfos-project-meta">
            <span>{projectId}</span>
            {phase ? <span>{phase}</span> : null}
          </p>
        </div>

        <div className="pfos-project-health-actions">
          <span className={statusClass(dashboardBlocked ? "attention" : "clear")}>
            {dashboardBlocked ? "Blocked" : "Ready"}
          </span>
          {onRefresh ? (
            <button type="button" onClick={onRefresh} disabled={isLoading}>
              {isLoading ? "Refreshing" : "Refresh"}
            </button>
          ) : null}
          {onRequestPhaseTransition ? (
            <button
              type="button"
              onClick={onRequestPhaseTransition}
              disabled={dashboardBlocked || isLoading}
            >
              Request transition
            </button>
          ) : null}
        </div>
      </header>

      {errorMessage ? (
        <p className="pfos-project-health-error" role="alert">
          {errorMessage}
        </p>
      ) : null}

      <dl className="pfos-health-summary">
        {summaryItems.map((item) => (
          <div className="pfos-health-summary-item" key={item.label}>
            <dt>{item.label}</dt>
            <dd>
              <strong>{item.value}</strong>
              <span className={statusClass(item.status)}>
                {statusLabel(item.status === "attention")}
              </span>
              <small>{item.detail}</small>
            </dd>
          </div>
        ))}
      </dl>

      <div className="pfos-health-detail-grid">
        <section className="pfos-health-section" aria-labelledby="queue-status-heading">
          <h3 id="queue-status-heading">Queue status</h3>
          <dl className="pfos-field-list">
            <div>
              <dt>Unprocessed outbox</dt>
              <dd>{health.outbox.unprocessed_count}</dd>
            </div>
            <div>
              <dt>Failed outbox</dt>
              <dd>{health.outbox.failed_count}</dd>
            </div>
            <div>
              <dt>Pending retractions</dt>
              <dd>{health.sourceRetractions.pending_count}</dd>
            </div>
            <div>
              <dt>Processing retractions</dt>
              <dd>{health.sourceRetractions.processing_count}</dd>
            </div>
            <div>
              <dt>Failed retractions</dt>
              <dd>{health.sourceRetractions.failed_count}</dd>
            </div>
          </dl>
        </section>

        <section className="pfos-health-section" aria-labelledby="approval-status-heading">
          <h3 id="approval-status-heading">Approval status</h3>
          {approvalStatus ? (
            <dl className="pfos-field-list">
              <div>
                <dt>Phase</dt>
                <dd>{approvalStatus.phase}</dd>
              </div>
              <div>
                <dt>Quorum</dt>
                <dd>{approvalStatus.quorum_met ? "Met" : "Open"}</dd>
              </div>
              <div>
                <dt>Approved</dt>
                <dd>
                  {approvalStatus.approved_count}/{approvalStatus.required_count}
                </dd>
              </div>
              <div>
                <dt>Rejected</dt>
                <dd>{approvalStatus.rejected_count}</dd>
              </div>
              <div>
                <dt>Escalation</dt>
                <dd>{approvalStatus.escalation_status}</dd>
              </div>
            </dl>
          ) : (
            <p className="pfos-empty-state">No phase approval snapshot selected.</p>
          )}
        </section>
      </div>

      <section className="pfos-health-section" aria-labelledby="hard-gate-heading">
        <h3 id="hard-gate-heading">Hard-gate checks</h3>
        <table className="pfos-hard-gate-table">
          <thead>
            <tr>
              <th scope="col">Check</th>
              <th scope="col">Status</th>
              <th scope="col">Reason</th>
            </tr>
          </thead>
          <tbody>
            {health.hardGates.checks.map((check) => (
              <tr key={check.name}>
                <th scope="row">{check.name}</th>
                <td>
                  <span
                    className={statusClass(
                      check.passed === false ? "attention" : "clear",
                    )}
                  >
                    {check.passed === false ? "Blocked" : "Clear"}
                  </span>
                </td>
                <td>{check.reason || "None"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </section>
  );
}

export default ProjectHealth;
