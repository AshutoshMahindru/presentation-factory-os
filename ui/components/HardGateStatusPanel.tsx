import type { HardGateCheck, HardGateStatus, JsonObject, JsonValue } from "../lib/api";
import { StaleArtifactNotice } from "./StaleArtifactNotice";

export interface HardGateStatusPanelProps {
  hardGates: HardGateStatus;
  isLoading?: boolean;
  errorMessage?: string | null;
}

type GateState = "clear" | "attention";

interface StaleArtifactCounts {
  totalCount: number;
  financialCellsCount: number;
  designTokensCount: number;
  isBlocked: boolean;
}

function statusClass(status: GateState): string {
  return `pfos-status pfos-status-${status}`;
}

function asNumber(value: JsonValue | undefined): number {
  return typeof value === "number" ? value : 0;
}

function formatMetadataValue(value: JsonValue): string {
  if (value === null) {
    return "None";
  }

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return JSON.stringify(value);
}

function metadataEntries(metadata: JsonObject | undefined): [string, JsonValue][] {
  if (!metadata) {
    return [];
  }

  return Object.entries(metadata);
}

function findStaleArtifactCounts(checks: HardGateCheck[]): StaleArtifactCounts | null {
  const staleCheck = checks.find((check) => check.name === "no_stale_downstream_artifacts");
  if (!staleCheck) {
    return null;
  }

  const metadata = staleCheck.metadata ?? {};
  const financialCellsCount = asNumber(metadata.financial_cells_count);
  const designTokensCount = asNumber(metadata.design_tokens_count);
  const totalCount = asNumber(metadata.total_count);
  const derivedTotalCount =
    totalCount > 0 ? totalCount : financialCellsCount + designTokensCount;

  return {
    totalCount: derivedTotalCount,
    financialCellsCount,
    designTokensCount,
    isBlocked: staleCheck.passed === false || derivedTotalCount > 0,
  };
}

export function HardGateStatusPanel({
  hardGates,
  isLoading = false,
  errorMessage = null,
}: HardGateStatusPanelProps) {
  const staleArtifactCounts = findStaleArtifactCounts(hardGates.checks);

  return (
    <section
      className="pfos-health-section"
      aria-labelledby="hard-gate-heading"
      aria-busy={isLoading}
    >
      <header className="pfos-inline-section-header">
        <div>
          <h3 id="hard-gate-heading">Hard-gate status</h3>
          <p>{hardGates.name || "no_blocking_rules"}</p>
        </div>
        <span className={statusClass(hardGates.passed ? "clear" : "attention")}>
          {hardGates.passed ? "Passed" : "Blocked"}
        </span>
      </header>

      {isLoading ? <p className="pfos-empty-state">Loading hard-gate status...</p> : null}
      {errorMessage ? (
        <p className="pfos-project-health-error" role="alert">
          {errorMessage}
        </p>
      ) : null}

      <dl className="pfos-field-list">
        <div>
          <dt>Checks evaluated</dt>
          <dd>{hardGates.checks.length}</dd>
        </div>
        <div>
          <dt>Failed checks</dt>
          <dd>{hardGates.failed_checks.length}</dd>
        </div>
        <div>
          <dt>Gate result</dt>
          <dd>{hardGates.passed ? "Pass" : "Fail"}</dd>
        </div>
      </dl>

      {staleArtifactCounts ? (
        <StaleArtifactNotice
          totalCount={staleArtifactCounts.totalCount}
          financialCellsCount={staleArtifactCounts.financialCellsCount}
          designTokensCount={staleArtifactCounts.designTokensCount}
          isBlocked={staleArtifactCounts.isBlocked}
        />
      ) : null}

      {hardGates.checks.length > 0 ? (
        <table className="pfos-hard-gate-table">
          <thead>
            <tr>
              <th scope="col">Check</th>
              <th scope="col">State</th>
              <th scope="col">Reason</th>
              <th scope="col">Metadata</th>
            </tr>
          </thead>
          <tbody>
            {hardGates.checks.map((check) => {
              const entries = metadataEntries(check.metadata);

              return (
                <tr key={check.name}>
                  <th scope="row">{check.name}</th>
                  <td>
                    <span
                      className={statusClass(
                        check.passed === false ? "attention" : "clear",
                      )}
                    >
                      {check.passed === false ? "Fail" : "Pass"}
                    </span>
                  </td>
                  <td>{check.reason || "None"}</td>
                  <td>
                    {entries.length > 0 ? (
                      <dl className="pfos-metadata-list">
                        {entries.map(([key, value]) => (
                          <div key={key}>
                            <dt>{key}</dt>
                            <dd>{formatMetadataValue(value)}</dd>
                          </div>
                        ))}
                      </dl>
                    ) : (
                      "None"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="pfos-empty-state">No hard-gate checks returned.</p>
      )}
    </section>
  );
}

export default HardGateStatusPanel;
