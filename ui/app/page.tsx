"use client";

import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import { AudienceIntakeForm } from "../components/AudienceIntakeForm";
import { PersonaSelector } from "../components/PersonaSelector";
import { ProjectHealth } from "../components/ProjectHealth";
import { ApiClientError, createPfosApiClient } from "../lib/api";
import type {
  ApprovalStatus,
  ChatPresentationResponse,
  CreateProjectResponse,
  PfosPhase,
  ProjectControlPlaneHealth,
} from "../lib/api";

const PHASE_OPTIONS: Array<PfosPhase | string> = [
  "intake",
  "strategy",
  "financial_model",
  "review",
];

function messageFromError(error: unknown): string {
  if (error instanceof ApiClientError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Unable to load project dashboard.";
}

export default function ProjectDashboardPage() {
  const [projectId, setProjectId] = useState("");
  const [phase, setPhase] = useState<PfosPhase | string>("review");
  const [health, setHealth] = useState<ProjectControlPlaneHealth | null>(null);
  const [approvalStatus, setApprovalStatus] = useState<ApprovalStatus | null>(null);
  const [createdProject, setCreatedProject] = useState<CreateProjectResponse | null>(null);
  const [presentationPrompt, setPresentationPrompt] = useState(
    "Create a 5 slide board deck for PFOS automation reliability.",
  );
  const [presentationRun, setPresentationRun] = useState<ChatPresentationResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isCreatingPresentation, setIsCreatingPresentation] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [presentationErrorMessage, setPresentationErrorMessage] = useState<string | null>(null);

  const apiClient = useMemo(
    () =>
      createPfosApiClient({
        baseUrl: process.env.NEXT_PUBLIC_PFOS_API_BASE_URL ?? "",
      }),
    [],
  );

  async function loadDashboard() {
    const normalizedProjectId = projectId.trim();
    if (!normalizedProjectId) {
      setHealth(null);
      setApprovalStatus(null);
      setErrorMessage("Enter a project ID to load the dashboard.");
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const [controlPlaneHealth, phaseApprovalStatus] = await Promise.all([
        apiClient.getProjectControlPlaneHealth(normalizedProjectId),
        apiClient.getApprovalStatus(normalizedProjectId, phase),
      ]);
      setHealth(controlPlaneHealth);
      setApprovalStatus(phaseApprovalStatus);
    } catch (error) {
      setHealth(null);
      setApprovalStatus(null);
      setErrorMessage(messageFromError(error));
    } finally {
      setIsLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadDashboard();
  }

  function handleProjectCreated(project: CreateProjectResponse) {
    setCreatedProject(project);
    setProjectId(project.project_id);
  }

  async function createPresentationPreview() {
    const content = presentationPrompt.trim();
    if (!content) {
      setPresentationRun(null);
      setPresentationErrorMessage("Enter a presentation prompt.");
      return;
    }

    setIsCreatingPresentation(true);
    setPresentationErrorMessage(null);

    try {
      const normalizedProjectId = projectId.trim();
      const run = await apiClient.createPresentationFromChat(
        {
          content,
          project_context: {
            decision_required: "Review and approve the proposed presentation direction.",
          },
        },
        normalizedProjectId || undefined,
      );
      setPresentationRun(run);
    } catch (error) {
      setPresentationRun(null);
      setPresentationErrorMessage(messageFromError(error));
    } finally {
      setIsCreatingPresentation(false);
    }
  }

  function handlePresentationSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void createPresentationPreview();
  }

  return (
    <main className="pfos-dashboard-page">
      <section className="pfos-dashboard-shell" aria-labelledby="dashboard-heading">
        <header className="pfos-dashboard-header">
          <div>
            <p className="pfos-kicker">Project dashboard</p>
            <h1 id="dashboard-heading">Operator control plane</h1>
          </div>
        </header>

        <div className="pfos-dashboard-intake-grid">
          <AudienceIntakeForm onProjectCreated={handleProjectCreated} />
          <PersonaSelector />
        </div>

        {createdProject ? (
          <p className="pfos-dashboard-created" role="status">
            Latest intake project: {createdProject.project_id}
          </p>
        ) : null}

        <form className="pfos-dashboard-query" onSubmit={handleSubmit}>
          <label>
            <span>Project ID</span>
            <input
              type="text"
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
              placeholder="7d8d6e74-7e0c-4e6b-9e68-7d4e4a8406d5"
              autoComplete="off"
            />
          </label>

          <label>
            <span>Approval phase</span>
            <select
              value={phase}
              onChange={(event) => setPhase(event.target.value)}
            >
              {PHASE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <button type="submit" disabled={isLoading}>
            {isLoading ? "Loading" : "Load dashboard"}
          </button>
        </form>

        <section className="pfos-presentation-chat" aria-labelledby="presentation-chat-heading">
          <div>
            <p className="pfos-kicker">Presentation chat</p>
            <h2 id="presentation-chat-heading">Create a deck preview</h2>
          </div>

          <form className="pfos-presentation-chat-form" onSubmit={handlePresentationSubmit}>
            <label>
              <span>Prompt</span>
              <textarea
                value={presentationPrompt}
                onChange={(event) => setPresentationPrompt(event.target.value)}
                rows={3}
              />
            </label>
            <button type="submit" disabled={isCreatingPresentation}>
              {isCreatingPresentation ? "Creating" : "Create preview"}
            </button>
          </form>

          {presentationErrorMessage ? (
            <p className="pfos-presentation-error" role="alert">
              {presentationErrorMessage}
            </p>
          ) : null}

          {presentationRun ? (
            <div className="pfos-presentation-result" aria-live="polite">
              <div>
                <span>Slides</span>
                <strong>{presentationRun.web_preview.slide_count}</strong>
              </div>
              <div>
                <span>Export</span>
                <strong>
                  {presentationRun.export_gate.export_allowed ? "Ready" : "Blocked"}
                </strong>
              </div>
              <div>
                <span>Preview hash</span>
                <code>{presentationRun.web_preview.content_hash.slice(0, 12)}</code>
              </div>
              <div className="pfos-presentation-result-wide">
                <span>Next action</span>
                <p>{presentationRun.recommended_next_action}</p>
              </div>
              {presentationRun.evidence_gaps.length > 0 ? (
                <div className="pfos-presentation-result-wide">
                  <span>Evidence gaps</span>
                  <ul>
                    {presentationRun.evidence_gaps.map((gap) => (
                      <li key={gap}>{gap}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>

        {health ? (
          <ProjectHealth
            projectId={projectId.trim()}
            phase={phase}
            health={health}
            approvalStatus={approvalStatus}
            isLoading={isLoading}
            errorMessage={errorMessage}
            onRefresh={loadDashboard}
          />
        ) : (
          <section className="pfos-dashboard-empty" aria-live="polite">
            <h2>Control-plane status</h2>
            <p>{errorMessage ?? "Enter a project ID to inspect queue, hard-gate, and approval status."}</p>
          </section>
        )}
      </section>

      <style>{`
        .pfos-dashboard-page {
          min-height: 100vh;
          background: #f6f7f9;
          color: #18202f;
          padding: 40px 20px;
        }

        .pfos-dashboard-shell {
          width: min(1120px, 100%);
          margin: 0 auto;
        }

        .pfos-dashboard-header {
          margin-bottom: 24px;
        }

        .pfos-dashboard-intake-grid {
          display: grid;
          grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr);
          gap: 16px;
          margin-bottom: 16px;
        }

        .pfos-intake-panel,
        .pfos-persona-panel {
          background: #ffffff;
          border: 1px solid #dce2ea;
          border-radius: 8px;
          padding: 16px;
        }

        .pfos-intake-panel header,
        .pfos-persona-panel header {
          margin-bottom: 14px;
        }

        .pfos-intake-panel h2,
        .pfos-persona-panel h2 {
          font-size: 20px;
          margin: 0;
        }

        .pfos-intake-form {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }

        .pfos-intake-form label {
          display: grid;
          gap: 6px;
          min-width: 0;
        }

        .pfos-intake-form-wide {
          grid-column: 1 / -1;
        }

        .pfos-intake-form span,
        .pfos-persona-summary dt {
          color: #536176;
          font-size: 12px;
          font-weight: 700;
        }

        .pfos-intake-form input,
        .pfos-intake-form textarea {
          border: 1px solid #c8d1dd;
          border-radius: 6px;
          color: #18202f;
          font: inherit;
          padding: 10px 12px;
        }

        .pfos-intake-form button {
          min-height: 40px;
          border: 0;
          border-radius: 6px;
          background: #147d64;
          color: #ffffff;
          cursor: pointer;
          font: inherit;
          font-weight: 700;
          padding: 0 16px;
        }

        .pfos-intake-form button:disabled {
          cursor: default;
          opacity: 0.62;
        }

        .pfos-intake-status,
        .pfos-dashboard-created {
          color: #405168;
          font-size: 13px;
          margin: 12px 0 0;
        }

        .pfos-dashboard-created {
          margin-bottom: 16px;
        }

        .pfos-persona-options {
          display: grid;
          gap: 8px;
        }

        .pfos-persona-options button {
          align-items: center;
          background: #f7f9fc;
          border: 1px solid #cfd8e3;
          border-radius: 6px;
          color: #18202f;
          cursor: pointer;
          display: flex;
          font: inherit;
          justify-content: space-between;
          min-height: 42px;
          padding: 0 12px;
          text-align: left;
        }

        .pfos-persona-options button.selected {
          background: #eaf3ff;
          border-color: #1f6feb;
        }

        .pfos-persona-options span {
          color: #536176;
          font-size: 12px;
          font-weight: 700;
        }

        .pfos-persona-summary {
          display: grid;
          gap: 8px;
          margin: 14px 0 0;
        }

        .pfos-persona-summary div {
          display: flex;
          justify-content: space-between;
          gap: 12px;
        }

        .pfos-persona-summary dd {
          margin: 0;
          text-align: right;
        }

        .pfos-kicker {
          margin: 0 0 8px;
          color: #5f6f89;
          font-size: 12px;
          font-weight: 700;
          letter-spacing: 0;
          text-transform: uppercase;
        }

        .pfos-dashboard-header h1 {
          margin: 0;
          font-size: clamp(28px, 5vw, 44px);
          line-height: 1;
        }

        .pfos-dashboard-query {
          display: grid;
          grid-template-columns: minmax(260px, 1fr) minmax(180px, 240px) auto;
          gap: 12px;
          align-items: end;
          margin-bottom: 20px;
          padding: 16px;
          background: #ffffff;
          border: 1px solid #dce2ea;
          border-radius: 8px;
        }

        .pfos-dashboard-query label {
          display: grid;
          gap: 6px;
          min-width: 0;
        }

        .pfos-dashboard-query label span {
          color: #536176;
          font-size: 12px;
          font-weight: 700;
        }

        .pfos-dashboard-query input,
        .pfos-dashboard-query select {
          min-height: 40px;
          border: 1px solid #c8d1dd;
          border-radius: 6px;
          color: #18202f;
          background: #ffffff;
          padding: 0 12px;
          font: inherit;
        }

        .pfos-dashboard-query button {
          min-height: 40px;
          border: 0;
          border-radius: 6px;
          background: #1f6feb;
          color: #ffffff;
          cursor: pointer;
          font: inherit;
          font-weight: 700;
          padding: 0 16px;
        }

        .pfos-dashboard-query button:disabled {
          cursor: default;
          opacity: 0.62;
        }

        .pfos-presentation-chat {
          background: #ffffff;
          border: 1px solid #dce2ea;
          border-radius: 8px;
          margin-bottom: 20px;
          padding: 16px;
        }

        .pfos-presentation-chat h2 {
          font-size: 22px;
          margin: 0 0 14px;
        }

        .pfos-presentation-chat-form {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 12px;
          align-items: end;
        }

        .pfos-presentation-chat-form label {
          display: grid;
          gap: 6px;
          min-width: 0;
        }

        .pfos-presentation-chat-form span,
        .pfos-presentation-result span {
          color: #536176;
          font-size: 12px;
          font-weight: 700;
        }

        .pfos-presentation-chat-form textarea {
          border: 1px solid #c8d1dd;
          border-radius: 6px;
          color: #18202f;
          font: inherit;
          line-height: 1.35;
          min-height: 92px;
          padding: 10px 12px;
          resize: vertical;
        }

        .pfos-presentation-chat-form button {
          min-height: 40px;
          border: 0;
          border-radius: 6px;
          background: #147d64;
          color: #ffffff;
          cursor: pointer;
          font: inherit;
          font-weight: 700;
          padding: 0 16px;
        }

        .pfos-presentation-chat-form button:disabled {
          cursor: default;
          opacity: 0.62;
        }

        .pfos-presentation-error {
          color: #9b1c1c;
          margin: 12px 0 0;
        }

        .pfos-presentation-result {
          border-top: 1px solid #e5eaf0;
          display: grid;
          gap: 14px;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          margin-top: 16px;
          padding-top: 16px;
        }

        .pfos-presentation-result div {
          display: grid;
          gap: 6px;
          min-width: 0;
        }

        .pfos-presentation-result strong,
        .pfos-presentation-result code {
          color: #18202f;
          font-size: 18px;
          font-weight: 800;
        }

        .pfos-presentation-result code {
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
          overflow-wrap: anywhere;
        }

        .pfos-presentation-result-wide {
          grid-column: 1 / -1;
        }

        .pfos-presentation-result p,
        .pfos-presentation-result ul {
          margin: 0;
        }

        .pfos-presentation-result ul {
          padding-left: 18px;
        }

        .pfos-dashboard-empty {
          background: #ffffff;
          border: 1px dashed #cbd5e1;
          border-radius: 8px;
          color: #5a6779;
          padding: 20px;
        }

        .pfos-dashboard-empty h2 {
          color: #18202f;
          font-size: 24px;
          margin: 0 0 8px;
        }

        .pfos-dashboard-empty p {
          margin: 0;
        }

        @media (max-width: 760px) {
          .pfos-dashboard-page {
            padding: 24px 14px;
          }

          .pfos-dashboard-query {
            grid-template-columns: 1fr;
          }

          .pfos-presentation-chat-form,
          .pfos-presentation-result {
            grid-template-columns: 1fr;
          }

          .pfos-dashboard-intake-grid,
          .pfos-intake-form {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </main>
  );
}
