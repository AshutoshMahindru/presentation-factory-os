import { PHASES } from "../lib/phaseTypes";
import type { Phase } from "../lib/phaseTypes";

export interface PhaseStepperProps {
  currentPhase?: Phase | string;
}

export function PhaseStepper({ currentPhase = "created" }: PhaseStepperProps) {
  const currentIndex = PHASES.findIndex((phase) => phase === currentPhase);

  return (
    <nav className="pfos-phase-stepper" aria-label="Project phase">
      <ol>
        {PHASES.map((phase, index) => {
          const status =
            currentIndex === -1
              ? "pending"
              : index < currentIndex
                ? "complete"
                : index === currentIndex
                  ? "current"
                  : "pending";
          return (
            <li aria-current={status === "current" ? "step" : undefined} data-status={status} key={phase}>
              {phase}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export default PhaseStepper;
