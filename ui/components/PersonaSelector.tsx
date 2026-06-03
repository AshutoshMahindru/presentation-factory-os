"use client";

import { useState } from "react";

export interface PersonaOption {
  id: string;
  title: string;
  time_budget_minutes: number;
  tone: string;
  decision_bias: string;
}

const PERSONA_OPTIONS: PersonaOption[] = [
  {
    id: "ic_partner",
    title: "IC partner",
    time_budget_minutes: 12,
    tone: "direct",
    decision_bias: "Risk-adjusted upside",
  },
  {
    id: "cfo",
    title: "CFO",
    time_budget_minutes: 8,
    tone: "precise",
    decision_bias: "Cash discipline",
  },
  {
    id: "board",
    title: "Board sponsor",
    time_budget_minutes: 15,
    tone: "strategic",
    decision_bias: "Durable advantage",
  },
];

export interface PersonaSelectorProps {
  onPersonaSelected?: (persona: PersonaOption) => void;
}

export function PersonaSelector({ onPersonaSelected }: PersonaSelectorProps) {
  const [selectedPersonaId, setSelectedPersonaId] = useState(PERSONA_OPTIONS[0].id);
  const selectedPersona =
    PERSONA_OPTIONS.find((persona) => persona.id === selectedPersonaId) ?? PERSONA_OPTIONS[0];

  function selectPersona(persona: PersonaOption) {
    setSelectedPersonaId(persona.id);
    onPersonaSelected?.(persona);
  }

  return (
    <section className="pfos-persona-panel" aria-labelledby="persona-selector-heading">
      <header>
        <p className="pfos-kicker">Persona selection</p>
        <h2 id="persona-selector-heading">Audience lens</h2>
      </header>

      <div className="pfos-persona-options" role="radiogroup" aria-label="Audience persona">
        {PERSONA_OPTIONS.map((persona) => (
          <button
            aria-checked={persona.id === selectedPersona.id}
            className={persona.id === selectedPersona.id ? "selected" : ""}
            key={persona.id}
            onClick={() => selectPersona(persona)}
            role="radio"
            type="button"
          >
            <strong>{persona.title}</strong>
            <span>{persona.time_budget_minutes} min</span>
          </button>
        ))}
      </div>

      <dl className="pfos-persona-summary">
        <div>
          <dt>Tone</dt>
          <dd>{selectedPersona.tone}</dd>
        </div>
        <div>
          <dt>Decision bias</dt>
          <dd>{selectedPersona.decision_bias}</dd>
        </div>
      </dl>
    </section>
  );
}

export default PersonaSelector;
