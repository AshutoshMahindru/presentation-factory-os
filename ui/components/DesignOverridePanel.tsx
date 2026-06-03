export interface DesignOverride {
  override_id: string;
  slide_id: string;
  field_path: string;
  actor: string;
  reason: string;
  triggers_reapproval: boolean;
  created_at: string;
}

export interface DesignOverridePanelProps {
  overrides: DesignOverride[];
  isLoading?: boolean;
}

export function DesignOverridePanel({
  overrides,
  isLoading = false,
}: DesignOverridePanelProps) {
  if (isLoading) {
    return (
      <section className="pfos-design-overrides" aria-busy="true">
        <h2>Design overrides</h2>
        <p>Loading audit trail.</p>
      </section>
    );
  }

  return (
    <section className="pfos-design-overrides" aria-labelledby="design-overrides-heading">
      <h2 id="design-overrides-heading">Design overrides</h2>
      {overrides.length === 0 ? (
        <p>No audited design overrides.</p>
      ) : (
        <ol>
          {overrides.map((override) => (
            <li key={override.override_id}>
              <strong>{override.slide_id}</strong>
              <span>{override.field_path}</span>
              <span>{override.actor}</span>
              <span>{override.reason}</span>
              {override.triggers_reapproval ? <span>Re-approval required</span> : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export default DesignOverridePanel;
