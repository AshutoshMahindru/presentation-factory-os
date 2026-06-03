"use client";

import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import { ProjectHealth } from "../components/ProjectHealth";
import { ApiClientError, createPfosApiClient } from "../lib/api";
import type { ApprovalStatus, PfosPhase, ProjectControlPlaneHealth } from "../lib/api";

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
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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

  return (
    <main className="pfos-dashboard-page">
      <section className="pfos-dashboard-shell" aria-labelledby="dashboard-heading">
        <header className="pfos-dashboard-header">
          <div>
            <p className="pfos-kicker">Project dashboard</p>
            <h1 id="dashboard-heading">Operator control plane</h1>
          </div>
        </header>

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
        }
      `}</style>
    </main>
  );
}
