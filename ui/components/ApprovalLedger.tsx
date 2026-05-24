import type { ApprovalStatus, PfosPhase } from "../lib/api";

export interface ApprovalLedgerProps {
  projectId?: string;
  phase?: PfosPhase | string;
  status?: ApprovalStatus | null;
  isLoading?: boolean;
  errorMessage?: string | null;
  onRefresh?: () => void;
}

interface LedgerDecisionRow {
  key: string;
  label: string;
  count: number;
  detail: string;
  tone: "clear" | "open" | "attention" | "neutral";
}

function humanizeToken(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function statusClass(tone: LedgerDecisionRow["tone"]): string {
  return `pfos-status pfos-status-${tone}`;
}

function buildDecisionRows(status: ApprovalStatus): LedgerDecisionRow[] {
  return [
    {
      key: "approved",
      label: "Approvals",
      count: status.approved_count,
      detail: "Entries counted toward quorum.",
      tone: status.quorum_met ? "clear" : "open",
    },
    {
      key: "rejected",
      label: "Rejections",
      count: status.rejected_count,
      detail: status.blocking_rejection
        ? "At least one rejection blocks quorum."
        : "Rejection entries in the current snapshot.",
      tone: status.rejected_count > 0 ? "attention" : "neutral",
    },
    {
      key: "abstained",
      label: "Abstentions",
      count: status.abstained_count,
      detail: "Recorded abstentions for this phase.",
      tone: status.abstained_count > 0 ? "open" : "neutral",
    },
    {
      key: "changes_requested",
      label: "Changes requested",
      count: status.changes_requested_count,
      detail: "Entries that require operator follow-up.",
      tone: status.changes_requested_count > 0 ? "attention" : "neutral",
    },
  ];
}

function missingRoleEntries(status: ApprovalStatus): Array<[string, number]> {
  return Object.entries(status.missing_roles).sort(([left], [right]) =>
    left.localeCompare(right),
  );
}

function escalationLabel(status: ApprovalStatus): string {
  if (status.escalation_status === "none") {
    return "None";
  }

  if (status.escalation_reason) {
    return humanizeToken(status.escalation_reason);
  }

  return humanizeToken(status.escalation_status);
}

export function ApprovalLedger({
  projectId,
  phase,
  status,
  isLoading = false,
  errorMessage = null,
  onRefresh,
}: ApprovalLedgerProps) {
  const selectedPhase = status?.phase ?? phase;
  const decisionRows = status ? buildDecisionRows(status) : [];
  const missingRoles = status ? missingRoleEntries(status) : [];
  const countedEntries = status
    ? status.approved_count +
      status.rejected_count +
      status.abstained_count +
      status.changes_requested_count
    : 0;

  return (
    <section
      className="pfos-approval-ledger"
      aria-labelledby="approval-ledger-heading"
      aria-busy={isLoading}
    >
      <header className="pfos-approval-ledger-header">
        <div>
          <p className="pfos-kicker">Approval quorum</p>
          <h2 id="approval-ledger-heading">Current ledger snapshot</h2>
          <p className="pfos-approval-meta">
            {projectId ? <span>{projectId}</span> : null}
            {selectedPhase ? <span>{selectedPhase}</span> : null}
          </p>
        </div>

        <div className="pfos-approval-actions">
          {status ? (
            <span className={statusClass(status.quorum_met ? "clear" : "open")}>
              {status.quorum_met ? "Quorum met" : "Quorum open"}
            </span>
          ) : null}
          {onRefresh ? (
            <button type="button" onClick={onRefresh} disabled={isLoading}>
              {isLoading ? "Refreshing" : "Refresh"}
            </button>
          ) : null}
        </div>
      </header>

      {errorMessage ? (
        <p className="pfos-approval-message pfos-approval-message-error" role="alert">
          {errorMessage}
        </p>
      ) : null}

      {isLoading && !status ? (
        <p className="pfos-approval-message pfos-approval-message-loading">
          Loading approval status.
        </p>
      ) : null}

      {!isLoading && !errorMessage && !status ? (
        <p className="pfos-approval-message pfos-approval-message-empty">
          Enter a project ID and phase to inspect the approval ledger.
        </p>
      ) : null}

      {status ? (
        <>
          <dl className="pfos-approval-summary">
            <div>
              <dt>Decision rule</dt>
              <dd>{humanizeToken(status.decision_rule)}</dd>
            </div>
            <div>
              <dt>Required approvals</dt>
              <dd>{status.required_count}</dd>
            </div>
            <div>
              <dt>Counted entries</dt>
              <dd>{countedEntries}</dd>
            </div>
            <div>
              <dt>Escalation</dt>
              <dd>{escalationLabel(status)}</dd>
            </div>
          </dl>

          <div className="pfos-approval-grid">
            <section className="pfos-approval-section" aria-labelledby="ledger-rows-heading">
              <h3 id="ledger-rows-heading">Ledger entries</h3>
              <table className="pfos-approval-table">
                <thead>
                  <tr>
                    <th scope="col">Decision</th>
                    <th scope="col">Status</th>
                    <th scope="col">Count</th>
                  </tr>
                </thead>
                <tbody>
                  {decisionRows.map((row) => (
                    <tr key={row.key}>
                      <th scope="row">
                        {row.label}
                        <p className="pfos-approval-detail">{row.detail}</p>
                      </th>
                      <td>
                        <span className={statusClass(row.tone)}>{humanizeToken(row.tone)}</span>
                      </td>
                      <td>{row.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="pfos-approval-section" aria-labelledby="missing-roles-heading">
              <h3 id="missing-roles-heading">Missing roles</h3>
              {missingRoles.length > 0 ? (
                <ul className="pfos-missing-role-list">
                  {missingRoles.map(([role, count]) => (
                    <li key={role}>
                      <span>{humanizeToken(role)}</span>
                      <strong>{count}</strong>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="pfos-approval-message pfos-approval-message-empty">
                  No required roles are missing.
                </p>
              )}
            </section>
          </div>

          <section className="pfos-approval-section" aria-labelledby="escalation-heading">
            <h3 id="escalation-heading">Escalation status</h3>
            <dl className="pfos-approval-summary">
              <div>
                <dt>Status</dt>
                <dd>{humanizeToken(status.escalation_status)}</dd>
              </div>
              <div>
                <dt>Reason</dt>
                <dd>
                  {status.escalation_reason
                    ? humanizeToken(status.escalation_reason)
                    : "None"}
                </dd>
              </div>
              <div>
                <dt>Blocking rejection</dt>
                <dd>{status.blocking_rejection ? "Yes" : "No"}</dd>
              </div>
              <div>
                <dt>Quorum</dt>
                <dd>{status.quorum_met ? "Met" : "Open"}</dd>
              </div>
            </dl>
          </section>
        </>
      ) : null}
    </section>
  );
}

export default ApprovalLedger;
