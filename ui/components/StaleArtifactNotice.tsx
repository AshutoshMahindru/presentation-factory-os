export const STALE_ARTIFACT_MESSAGE =
  "This artifact was drafted before an upstream phase was revised and requires revalidation before it can be used for approval or export.";

export interface StaleArtifactNoticeProps {
  totalCount?: number;
  financialCellsCount?: number;
  designTokensCount?: number;
  isBlocked?: boolean;
}

export function StaleArtifactNotice({
  totalCount = 0,
  financialCellsCount = 0,
  designTokensCount = 0,
  isBlocked = totalCount > 0,
}: StaleArtifactNoticeProps) {
  if (!isBlocked && totalCount <= 0) {
    return null;
  }

  return (
    <aside className="pfos-stale-artifact-notice" role="status" aria-live="polite">
      <div>
        <p className="pfos-kicker">Stale artifact warning</p>
        <h4>Revalidation required</h4>
      </div>
      <p>{STALE_ARTIFACT_MESSAGE}</p>
      <dl className="pfos-field-list">
        <div>
          <dt>Total stale artifacts</dt>
          <dd>{totalCount}</dd>
        </div>
        <div>
          <dt>Financial cells</dt>
          <dd>{financialCellsCount}</dd>
        </div>
        <div>
          <dt>Design tokens</dt>
          <dd>{designTokensCount}</dd>
        </div>
      </dl>
    </aside>
  );
}

export default StaleArtifactNotice;
