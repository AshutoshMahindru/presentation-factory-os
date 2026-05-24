"use client";

import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import { ApprovalLedger } from "../../components/ApprovalLedger";
import { ApiClientError, createPfosApiClient } from "../../lib/api";
import type { ApprovalStatus, PfosPhase } from "../../lib/api";

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

  return "Unable to load approval status.";
}

export default function ApprovalsPage() {
  const [projectId, setProjectId] = useState("");
  const [phase, setPhase] = useState<PfosPhase | string>("review");
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

  async function loadApprovalStatus() {
    const normalizedProjectId = projectId.trim();
    if (!normalizedProjectId) {
      setApprovalStatus(null);
      setErrorMessage("Enter a project ID to load approval status.");
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const status = await apiClient.getApprovalStatus(normalizedProjectId, phase);
      setApprovalStatus(status);
    } catch (error) {
      setApprovalStatus(null);
      setErrorMessage(messageFromError(error));
    } finally {
      setIsLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadApprovalStatus();
  }

  return (
    <main className="pfos-approvals-page">
      <section className="pfos-approvals-shell" aria-labelledby="approvals-heading">
        <header className="pfos-approvals-header">
          <div>
            <p className="pfos-kicker">Operator approvals</p>
            <h1 id="approvals-heading">Approval ledger</h1>
          </div>
        </header>

        <form className="pfos-approval-query" onSubmit={handleSubmit}>
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
            <span>Phase</span>
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
            {isLoading ? "Loading" : "Load status"}
          </button>
        </form>

        <ApprovalLedger
          projectId={projectId.trim()}
          phase={phase}
          status={approvalStatus}
          isLoading={isLoading}
          errorMessage={errorMessage}
          onRefresh={approvalStatus ? loadApprovalStatus : undefined}
        />
      </section>

      <style>{`
        .pfos-approvals-page {
          min-height: 100vh;
          background: #f6f7f9;
          color: #18202f;
          padding: 40px 20px;
        }

        .pfos-approvals-shell {
          width: min(1120px, 100%);
          margin: 0 auto;
        }

        .pfos-approvals-header {
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 24px;
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

        .pfos-approvals-header h1 {
          margin: 0;
          font-size: clamp(28px, 5vw, 44px);
          line-height: 1;
        }

        .pfos-approval-query {
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

        .pfos-approval-query label {
          display: grid;
          gap: 6px;
          min-width: 0;
        }

        .pfos-approval-query label span {
          color: #536176;
          font-size: 12px;
          font-weight: 700;
        }

        .pfos-approval-query input,
        .pfos-approval-query select {
          min-height: 40px;
          border: 1px solid #c8d1dd;
          border-radius: 6px;
          color: #18202f;
          background: #ffffff;
          padding: 0 12px;
          font: inherit;
        }

        .pfos-approval-query button,
        .pfos-approval-actions button {
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

        .pfos-approval-query button:disabled,
        .pfos-approval-actions button:disabled {
          cursor: default;
          opacity: 0.62;
        }

        .pfos-approval-ledger {
          background: #ffffff;
          border: 1px solid #dce2ea;
          border-radius: 8px;
          padding: 20px;
        }

        .pfos-approval-ledger-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 20px;
          margin-bottom: 20px;
        }

        .pfos-approval-ledger h2,
        .pfos-approval-section h3 {
          margin: 0;
        }

        .pfos-approval-ledger h2 {
          font-size: 24px;
        }

        .pfos-approval-meta {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin: 8px 0 0;
          color: #5f6f89;
          font-size: 13px;
        }

        .pfos-approval-actions {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .pfos-status {
          display: inline-flex;
          align-items: center;
          min-height: 28px;
          border-radius: 999px;
          padding: 0 10px;
          font-size: 12px;
          font-weight: 800;
        }

        .pfos-status-clear {
          background: #daf5e5;
          color: #116332;
        }

        .pfos-status-open {
          background: #fff3c4;
          color: #7a4d00;
        }

        .pfos-status-attention {
          background: #ffe0e0;
          color: #9e1c1c;
        }

        .pfos-status-neutral {
          background: #edf1f6;
          color: #4d5d73;
        }

        .pfos-approval-message {
          border-radius: 8px;
          margin: 0;
          padding: 16px;
        }

        .pfos-approval-message-error {
          background: #fff0f0;
          color: #8a1f1f;
          border: 1px solid #ffcaca;
        }

        .pfos-approval-message-empty,
        .pfos-approval-message-loading {
          background: #f6f8fb;
          color: #5a6779;
          border: 1px dashed #cbd5e1;
        }

        .pfos-approval-summary {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 12px;
          margin: 0 0 20px;
        }

        .pfos-approval-summary div {
          border: 1px solid #dce2ea;
          border-radius: 8px;
          padding: 14px;
        }

        .pfos-approval-summary dt {
          color: #5f6f89;
          font-size: 12px;
          font-weight: 700;
          margin-bottom: 8px;
        }

        .pfos-approval-summary dd {
          margin: 0;
          font-size: 20px;
          font-weight: 800;
        }

        .pfos-approval-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
        }

        .pfos-approval-section {
          border-top: 1px solid #dce2ea;
          padding-top: 16px;
        }

        .pfos-missing-role-list {
          display: grid;
          gap: 8px;
          list-style: none;
          margin: 14px 0 0;
          padding: 0;
        }

        .pfos-missing-role-list li {
          display: flex;
          justify-content: space-between;
          gap: 16px;
          border: 1px solid #dce2ea;
          border-radius: 6px;
          padding: 10px 12px;
        }

        .pfos-approval-table {
          width: 100%;
          margin-top: 12px;
          border-collapse: collapse;
        }

        .pfos-approval-table th,
        .pfos-approval-table td {
          border-bottom: 1px solid #e6ebf1;
          padding: 12px 8px;
          text-align: left;
          vertical-align: top;
        }

        .pfos-approval-table th:last-child,
        .pfos-approval-table td:last-child {
          text-align: right;
        }

        .pfos-approval-detail {
          margin: 4px 0 0;
          color: #5f6f89;
          font-size: 13px;
        }

        @media (max-width: 760px) {
          .pfos-approval-query,
          .pfos-approval-summary,
          .pfos-approval-grid {
            grid-template-columns: 1fr;
          }

          .pfos-approval-ledger-header {
            flex-direction: column;
          }
        }
      `}</style>
    </main>
  );
}
