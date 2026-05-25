// Generated from docs/08_StateMachine_Spec.yaml by scripts/generate_phase_enums.py. Do not edit by hand.

export const PHASES = [
  "created",
  "intake",
  "strategy",
  "research",
  "financial_model",
  "narrative",
  "visual_design",
  "review",
  "approved",
  "exported",
  "rejected",
] as const;

export type Phase = (typeof PHASES)[number];

export function isPhase(value: string): value is Phase {
  return (PHASES as readonly string[]).includes(value);
}
