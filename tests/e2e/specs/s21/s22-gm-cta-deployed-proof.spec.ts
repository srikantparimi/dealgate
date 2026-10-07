/**
 * Deployed proof for the recurring Staffing & GM calculation/CTA defects.
 *
 * The fixture is server-issued and deleted in `finally`. Feature responses
 * are never mocked: this drives the deployed SPA, API, RDS and commercial
 * calculation service with a real SOW version and a persisted working draft.
 */
import { expect, request as pwRequest, test, type APIRequestContext } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { authAsRole, bearerFor, type RoleSlot } from "../../fixtures/multi-role-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const REPO = path.resolve(__dirname, "..", "..", "..", "..");
const SOURCE_SOW = path.join(REPO, "fixtures/sample_sows/08_assessment_fixed_fee.docx");
const EVIDENCE = path.join(REPO, "docs/s21/evidence/staging/s22-gm-cta");
const REQUIRED_FIELDS = [
  "client_legal_name",
  "client_domain",
  "billing_basis_normalized",
  "scope_summary",
  "price",
  "currency",
  "billing_basis",
  "term_start",
  "term_end",
  "notice_date",
  "deliverables",
  "milestones",
  "acceptance_criteria",
  "assumptions",
  "exclusions",
  "signatories",
  "engagement_type_suggested",
] as const;

async function apiFor(role: RoleSlot): Promise<APIRequestContext> {
  return pwRequest.newContext({
    baseURL: `${BASE}/api/`,
    extraHTTPHeaders: bearerFor(role),
  });
}

async function json<T>(response: import("@playwright/test").APIResponse): Promise<T> {
  if (!response.ok()) {
    throw new Error(`${response.status()} ${response.url()}\n${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

async function uploadSow(api: APIRequestContext, clientId: string, opportunityId: string) {
  const upload = await json<{ status?: string; job_id?: string; sow_version_id?: string }>(
    await api.post("sows/upload", {
      multipart: {
        client_id: clientId,
        opportunity_id: opportunityId,
        file: {
          name: `s22-gm-proof-${Date.now()}.docx`,
          mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          buffer: fs.readFileSync(SOURCE_SOW),
        },
      },
      timeout: 300_000,
    }),
  );
  if (upload.status === "done" && upload.sow_version_id) return upload.sow_version_id;
  expect(upload.job_id, "asynchronous upload must return a job id").toBeTruthy();
  for (let attempt = 0; attempt < 90; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2_000));
    const job = await json<{ status: string; error?: string; sow_version_id?: string }>(
      await api.get(`sows/jobs/${upload.job_id}`),
    );
    if (job.status === "done" && job.sow_version_id) return job.sow_version_id;
    if (job.status === "failed") throw new Error(`SOW extraction failed: ${job.error}`);
  }
  throw new Error(`SOW extraction job ${upload.job_id} did not finish`);
}

async function deleteAndDrain(api: APIRequestContext, clientId: string) {
  const response = await api.delete(`clients/${clientId}`, {
    params: { reason: "S22 GM CTA deployed proof teardown" },
  });
  if (response.status() === 404) return;
  const body = await json<{ job_id: string }>(response);
  for (let attempt = 0; attempt < 75; attempt += 1) {
    const state = await json<{ status: string; error?: string }>(
      await api.get(`deletion-jobs/${body.job_id}`),
    );
    if (state.status === "done") return;
    if (state.status === "failed") throw new Error(`cleanup failed: ${state.error}`);
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
  throw new Error(`cleanup job ${body.job_id} did not drain`);
}

test("fixed-fee staffing calculates, persists and advances without a CTA loop", async ({ page }) => {
  test.setTimeout(600_000);
  fs.mkdirSync(EVIDENCE, { recursive: true });
  const api = await apiFor("system");
  let clientId = "";
  try {
    const reviewerIds: string[] = [];
    for (const role of ["system", "delivery", "hr", "finance", "legal", "submitter"] as const) {
      const roleApi = await apiFor(role);
      const me = await json<{ id: string }>(await roleApi.get("me"));
      reviewerIds.push(me.id);
      await roleApi.dispose();
    }
    expect(new Set(reviewerIds).size, "review transition needs distinct deployed identities").toBe(6);

    const fixture = await json<{ client_id: string; opportunity_id: string }>(
      await api.post("dev/test-fixtures", {
        data: {
          label: `S22 GM CTA proof ${new Date().toISOString()}`,
          reviewer_ids: [...new Set(reviewerIds)],
          hours: 2,
        },
      }),
    );
    clientId = fixture.client_id;
    const opportunityId = fixture.opportunity_id;
    const sowVersionId = await uploadSow(api, clientId, opportunityId);
    const detail = await json<{
      sow_id: string;
      extracted_fields: Record<string, { value: unknown }>;
    }>(await api.get(`sow/versions/${sowVersionId}`));
    const overrides: Partial<Record<(typeof REQUIRED_FIELDS)[number], unknown>> = {
      price: "75400",
      currency: "USD",
      billing_basis: "fixed fee",
      billing_basis_normalized: "fixed_fee",
      term_start: "2026-10-01",
      term_end: "2026-10-31",
      notice_date: "2026-10-15",
      signatories: [{ name: "E2E Client Signatory", role: "Client" }],
      engagement_type_suggested: "fixed_price",
    };
    for (const field of REQUIRED_FIELDS) {
      const value = overrides[field] ?? detail.extracted_fields[field]?.value;
      expect(value, `extraction must provide ${field}`).not.toBeUndefined();
      await json(
        await api.patch(`sow/versions/${sowVersionId}/fields/${field}`, {
          data: { value },
        }),
      );
    }
    await json(await api.post(`sow/versions/${sowVersionId}/submit`));

    const registry = await json<{ policy: { version: string } }>(
      await api.get("delivery-model/commercial/profiles"),
    );
    const binding = {
      source_id: detail.sow_id,
      source_version: sowVersionId,
      component_id: "s22-gm-cta-proof",
      profile_version: "1",
      policy_version: registry.policy.version,
    };
    const role = (id: string, name: string, quantity: number, allocation: string) => ({
      ...binding,
      assignment_id: id,
      role: name,
      seniority: name.startsWith("Senior") ? "Senior" : "Consultant",
      location: "India",
      timezone: "America/Los_Angeles",
      currency: "USD",
      quantity,
      allocation,
      calendar: null,
      hours_billable: null,
      bill_rate: null,
      cost_rate: "30",
      rate_version: null,
      cost_version: "S22 proof rate card v1",
      start: "2026-10-01",
      end: "2026-10-31",
      cost_rate_basis: "hourly",
      cost_proration: null,
    });
    const inputs = {
      ...binding,
      version: "1",
      workstream_id: "delivery",
      profile: "fixed_assignment",
      source_evidence: [`sow-version:${sowVersionId}:confirmed fixed fee and term`],
      service_start: "2026-10-01",
      service_end: "2026-10-31",
      timezone: "America/Los_Angeles",
      currency: "USD",
      billing_cadence: "fixed_post_delivery",
      cost_basis: null,
      costs_confirmed: true,
      costs: [],
      pricing: {
        total_fee: "75400",
        allocations: [{ month: "2026-10-01", location: "India", weight: "1" }],
        allocation_basis: "single October service month",
        minor_unit: "0.01",
      },
      staffing: (() => {
        const legacyCalendar = {
          calendar_id: "legacy-empty",
          version: "draft",
          timezone: "America/Los_Angeles",
          coverage_start: "2026-10-01",
          coverage_end: "2026-10-31",
          week: Array.from({ length: 7 }, () => ({
            scheduled: "",
            billable: "",
            paid: "",
          })),
          overrides: [],
        };
        return [
          {
            ...role("india-senior", "Senior consultant", 2, "1"),
            calendar: legacyCalendar,
          },
          role("india-partial", "Consultant", 1, "0.5"),
        ];
      })(),
    };
    await json(
      await api.put(`delivery-model/${opportunityId}/commercial/draft`, {
        data: { inputs, sow_version_id: sowVersionId, expected_updated_at: null },
      }),
    );

    await authAsRole(page, "system");
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(`${BASE}/sows/${opportunityId}/staffing`);
    await expect(page.getByTestId("draft-restored-banner")).toBeVisible({ timeout: 30_000 });
    const gm = page.getByRole("region", { name: "GM summary" });
    await expect(gm).toContainText("Contract price");
    await expect(gm).toContainText("$75,400");
    await expect(page.getByText(/validation errors for PricingComponent/)).toHaveCount(0);
    await expect(page.getByText("Cost basis", { exact: true })).toHaveCount(0);
    await expect(page.getByText(/Monthly plan & expenses/)).toHaveCount(0);
    await expect(page.getByText(/working calendar/i)).toHaveCount(0);
    const blocker = page.getByRole("button", { name: "Fix row 1 hours" });
    await expect(blocker).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: path.join(EVIDENCE, "01-before-known-revenue-and-row-blocker.png") });

    await blocker.click();
    await expect(page.getByLabel("Hours 1")).toBeFocused();
    await page.getByLabel("Hours 1").fill("176");
    await page.getByLabel("Hours 2").fill("176");
    await page.getByRole("button", { name: "Add cost" }).click();
    await page.getByLabel("Additional cost description 1").fill("Travel");
    await page.getByLabel("Additional cost amount 1").fill("2500");
    await page.getByLabel("Additional cost location 1").selectOption("India");

    const expectedRevenue = 75_400;
    const weekdayHours = 22 * 8;
    const expectedLabor = weekdayHours * 30 * (2 + 0.5);
    const expectedDirectCost = 2_500;
    const expectedCost = expectedLabor + expectedDirectCost;
    const expectedProfit = expectedRevenue - expectedCost;
    const expectedGm = expectedProfit / expectedRevenue;
    expect(expectedLabor).toBe(13_200);
    expect(expectedCost).toBe(15_700);
    expect(expectedGm).toBeCloseTo(0.791777188, 8);

    const saveAction = page.getByRole("button", { name: "Save", exact: true }).first();
    await expect(saveAction).toBeVisible({ timeout: 45_000 });
    await expect(gm).toContainText(`$${expectedLabor.toLocaleString("en-US")}`);
    await expect(gm).toContainText(`$${expectedDirectCost.toLocaleString("en-US")}`);
    await expect(gm).toContainText(`$${expectedCost.toLocaleString("en-US")}`);
    await expect(gm).toContainText(`$${expectedProfit.toLocaleString("en-US")}`);
    await expect(gm).toContainText("79.2%");
    await page.screenshot({ path: path.join(EVIDENCE, "02-calculated-financials-save-action.png") });

    await saveAction.click();
    await expect(page).toHaveURL(new RegExp(`/sows/new\\?opportunityId=${opportunityId}`), {
      timeout: 45_000,
    });
    await expect(page.getByRole("heading", { name: "Confirm SOW" })).toBeVisible();
    await expect(page.getByTestId("field-row-term_start")).toContainText("2026-10-01");
    await expect(page.getByTestId("field-row-term_end")).toContainText("2026-10-31");
    await expect(page.locator("#section-staffing")).toContainText("79.2%");
    const approvalPath = page.locator("#section-approvers");
    for (const label of ["Delivery", "HR", "Finance", "Legal"]) {
      await expect(approvalPath).toContainText(label);
    }
    await expect(approvalPath).toContainText("Not required");
    await expect(page.getByRole("button", { name: "Submit for approval" })).toHaveCount(0);
    await page.screenshot({ path: path.join(EVIDENCE, "03-confirm-sow-dates-gm-and-approval-path.png") });

    await page.reload();
    await expect(page.getByRole("heading", { name: "Confirm SOW" })).toBeVisible({ timeout: 45_000 });
    await expect(page.getByTestId("field-row-term_start")).toContainText("2026-10-01");
    await expect(page.getByTestId("field-row-term_end")).toContainText("2026-10-31");
    await expect(page.locator("#section-staffing")).toContainText("79.2%");

    await page.getByRole("button", { name: "Complete scope" }).click();
    await expect(page).toHaveURL(new RegExp(`/sows/${opportunityId}/approvals`), { timeout: 45_000 });
    await expect(page.getByRole("button", { name: "Submit for approval" })).toBeVisible({ timeout: 45_000 });

    await page.getByRole("button", { name: "Submit for approval" }).click();
    await expect(page.getByRole("heading", { name: "Submit for approval" })).toBeVisible();
    const reviewerPlan = page.getByRole("region", { name: "Planned reviewers" });
    await expect(reviewerPlan.getByText(/Frozen package: SOW v\d+ · GM v\d+/)).toBeVisible();
    const selects = reviewerPlan.locator("select");
    expect(await selects.count()).toBe(5);
    for (let i = 0; i < 5; i += 1) await expect(selects.nth(i)).not.toHaveValue("");
    await reviewerPlan.getByRole("button", { name: "Confirm submission" }).click();
    await expect(page).toHaveURL(new RegExp(`/sows/${opportunityId}/approvals`), { timeout: 45_000 });
    await expect(page.getByRole("button", { name: "View review status" })).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText(/Submitted by/).first()).toBeVisible();
    await expect(page.getByText(/Pending with|Queued for/).first()).toBeVisible();
    await page.screenshot({ path: path.join(EVIDENCE, "04-approvals-pipeline-status.png") });
  } finally {
    if (clientId) await deleteAndDrain(api, clientId);
    await api.dispose();
  }
});
