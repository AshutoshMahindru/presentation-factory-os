export interface RubricScore {
  dimension: string;
  score: number;
  status: "pass" | "warning" | "fail" | string;
}

export interface RubricPanelProps {
  scores?: RubricScore[];
}

export function RubricPanel({ scores = [] }: RubricPanelProps) {
  return (
    <section className="pfos-rubric-panel" aria-labelledby="rubric-panel-heading">
      <h2 id="rubric-panel-heading">Rubric panel</h2>
      {scores.length === 0 ? (
        <p>No rubric scores loaded.</p>
      ) : (
        <dl>
          {scores.map((score) => (
            <div key={score.dimension}>
              <dt>{score.dimension}</dt>
              <dd>
                {score.score} ({score.status})
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

export default RubricPanel;
