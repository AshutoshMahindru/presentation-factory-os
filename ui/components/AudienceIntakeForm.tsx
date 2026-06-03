"use client";

import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import { ApiClientError, createPfosApiClient } from "../lib/api";
import type { AudienceProfilePayload, CreateProjectResponse } from "../lib/api";

const DEFAULT_AUDIENCE_PROFILE: AudienceProfilePayload = {
  decision_maker_type: "ic_partner",
  risk_tolerance: "medium",
  familiarity_with_topic: "informed",
  known_objections: ["market_size"],
  stakeholder_map: [
    {
      role: "economic_buyer",
      concern: "Return on invested capital",
      influence_level: "high",
    },
  ],
};

function parseList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function messageFromError(error: unknown): string {
  if (error instanceof ApiClientError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unable to submit audience intake.";
}

export interface AudienceIntakeFormProps {
  onProjectCreated?: (project: CreateProjectResponse) => void;
}

export function AudienceIntakeForm({ onProjectCreated }: AudienceIntakeFormProps) {
  const [projectName, setProjectName] = useState("PFOS v2 operator intake");
  const [audience, setAudience] = useState("Investment committee");
  const [clientName, setClientName] = useState("");
  const [decisionRequired, setDecisionRequired] = useState("Approve the export-ready thesis deck.");
  const [knownObjections, setKnownObjections] = useState("market_size, timing");
  const [stakeholderConcern, setStakeholderConcern] = useState("Return on invested capital");
  const [initialMessage, setInitialMessage] = useState("Build an IC-ready thesis narrative with validated financial references.");
  const [createdProject, setCreatedProject] = useState<CreateProjectResponse | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const apiClient = useMemo(
    () =>
      createPfosApiClient({
        baseUrl: process.env.NEXT_PUBLIC_PFOS_API_BASE_URL ?? "",
      }),
    [],
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setStatusMessage(null);

    const audienceProfile: AudienceProfilePayload = {
      ...DEFAULT_AUDIENCE_PROFILE,
      known_objections: parseList(knownObjections),
      stakeholder_map: [
        {
          ...DEFAULT_AUDIENCE_PROFILE.stakeholder_map[0],
          concern: stakeholderConcern.trim() || DEFAULT_AUDIENCE_PROFILE.stakeholder_map[0].concern,
        },
      ],
    };

    try {
      const project = await apiClient.createProject({
        name: projectName.trim(),
        audience: audience.trim(),
        audience_profile: audienceProfile,
        client_name: clientName.trim() || null,
        decision_required: decisionRequired.trim() || null,
      });
      setCreatedProject(project);
      onProjectCreated?.(project);

      if (initialMessage.trim()) {
        await apiClient.appendIntakeChatMessage(project.project_id, {
          content: initialMessage.trim(),
          metadata: { source: "operator_dashboard" },
        });
      }

      setStatusMessage(`Created project ${project.project_id} in ${project.phase}.`);
    } catch (error) {
      setCreatedProject(null);
      setStatusMessage(messageFromError(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="pfos-intake-panel" aria-labelledby="audience-intake-heading">
      <header>
        <p className="pfos-kicker">Audience intake</p>
        <h2 id="audience-intake-heading">Create project profile</h2>
      </header>

      <form className="pfos-intake-form" onSubmit={handleSubmit}>
        <label>
          <span>Project name</span>
          <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
        </label>
        <label>
          <span>Audience</span>
          <input value={audience} onChange={(event) => setAudience(event.target.value)} />
        </label>
        <label>
          <span>Client</span>
          <input value={clientName} onChange={(event) => setClientName(event.target.value)} />
        </label>
        <label>
          <span>Decision required</span>
          <input
            value={decisionRequired}
            onChange={(event) => setDecisionRequired(event.target.value)}
          />
        </label>
        <label>
          <span>Known objections</span>
          <input
            value={knownObjections}
            onChange={(event) => setKnownObjections(event.target.value)}
          />
        </label>
        <label>
          <span>Primary concern</span>
          <input
            value={stakeholderConcern}
            onChange={(event) => setStakeholderConcern(event.target.value)}
          />
        </label>
        <label className="pfos-intake-form-wide">
          <span>Initial intake message</span>
          <textarea
            value={initialMessage}
            onChange={(event) => setInitialMessage(event.target.value)}
            rows={3}
          />
        </label>
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Submitting" : "Create intake"}
        </button>
      </form>

      {statusMessage ? (
        <p className="pfos-intake-status" role={createdProject ? "status" : "alert"}>
          {statusMessage}
        </p>
      ) : null}
    </section>
  );
}

export default AudienceIntakeForm;
