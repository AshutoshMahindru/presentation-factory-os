export interface EvidenceCoverageItem {
  pillar_id: string;
  covered: boolean;
  source_count: number;
}

export interface EvidenceCoverageProps {
  items?: EvidenceCoverageItem[];
}

export function EvidenceCoverage({ items = [] }: EvidenceCoverageProps) {
  const uncovered = items.filter((item) => !item.covered).length;

  return (
    <section className="pfos-evidence-coverage" aria-labelledby="evidence-coverage-heading">
      <h2 id="evidence-coverage-heading">Evidence coverage</h2>
      <p>
        {items.length} pillars checked, {uncovered} uncovered.
      </p>
      {items.length > 0 ? (
        <ul>
          {items.map((item) => (
            <li key={item.pillar_id}>
              <span>{item.pillar_id}</span>
              <strong>{item.covered ? "Covered" : "Missing evidence"}</strong>
              <small>{item.source_count} sources</small>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export default EvidenceCoverage;
