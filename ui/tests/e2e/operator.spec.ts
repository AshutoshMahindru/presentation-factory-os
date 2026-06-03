import { expect, test } from "@playwright/test";

const projectId = "7d8d6e74-7e0c-4e6b-9e68-7d4e4a8406d5";

const outboxStatus = {
  project_id: projectId,
  blocked: false,
  unprocessed_count: 0,
  failed_count: 0,
  oldest_unprocessed_age_seconds: null,
  pending_rows: [],
  failed_rows: []
};

const sourceRetractionStatus = {
  project_id: projectId,
  blocked: false,
  pending_count: 0,
  processing_count: 0,
  failed_count: 0,
  oldest_open_age_seconds: null,
  pending_events: [],
  failed_events: [],
  blocked_events: []
};

const hardGateStatus = {
  project_id: projectId,
  name: "export_readiness",
  passed: true,
  checks: [
    {
      name: "visual_qa_passed",
      passed: true,
      reason: null,
      metadata: {}
    }
  ],
  failed_checks: []
};

const approvalStatus = {
  project_id: projectId,
  phase: "review",
  quorum_met: true,
  decision_rule: "simple_majority",
  required_count: 2,
  approved_count: 2,
  rejected_count: 0,
  abstained_count: 0,
  changes_requested_count: 0,
  missing_roles: {},
  blocking_rejection: false,
  escalation_status: "none",
  escalation_reason: null
};

async function mockDashboardApi(page: import("@playwright/test").Page) {
  await page.route("**/health/projects/*/outbox", async (route) => {
    await route.fulfill({ json: outboxStatus });
  });
  await page.route("**/health/projects/*/source-retractions", async (route) => {
    await route.fulfill({ json: sourceRetractionStatus });
  });
  await page.route("**/health/projects/*/hard-gates", async (route) => {
    await route.fulfill({ json: hardGateStatus });
  });
  await page.route("**/projects/*/approvals/status/*", async (route) => {
    await route.fulfill({ json: approvalStatus });
  });
}

test("dashboard renders operator control plane without backend", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Operator control plane" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Create project profile" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Audience lens" })).toBeVisible();
});

test("dashboard load flow uses mocked project health and approval APIs", async ({ page }) => {
  await mockDashboardApi(page);
  await page.goto("/");

  await page.getByLabel("Project ID").fill(projectId);
  await page.getByRole("button", { name: "Load dashboard" }).click();

  await expect(page.getByRole("heading", { name: "Control-plane status" })).toBeVisible();
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Queue status" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hard-gate status" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Approval status" })).toBeVisible();
  await expect(page.getByText("Met", { exact: true })).toBeVisible();
});

test("approvals page renders and loads mocked quorum status", async ({ page }) => {
  await mockDashboardApi(page);
  await page.goto("/approvals");

  await expect(page.getByRole("heading", { name: "Approval ledger" })).toBeVisible();
  await page.getByLabel("Project ID").fill(projectId);
  await page.getByRole("button", { name: "Load status" }).click();

  await expect(page.getByText("Quorum met")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ledger entries" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Missing roles" })).toBeVisible();
});
