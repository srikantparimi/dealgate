/**
 * S22 P4-4 (and P4-2 / P4-5 on the way) · upload the sheet, on the deployed SPA.
 *
 *   New engagement → upload the sample staff-aug sheet → lands on the engagement with the
 *   "Imported from the sheet" note → five people → PASS.
 *   New engagement → upload the product owner's older copy (Peppermill assessment, no Employment
 *   type column, no holidays) → note says "Sheet said 168 h for Vikrin; the app computes 160 h …
 *   2026-09-07" → Forecast tab shows the whole-term summary first, "Show month split" reveals the
 *   months, per-person rows are hours (fixed-fee type).
 *
 * Accounts are server-issued fixtures named after the sheets' clients (S21 runtime isolation);
 * teardown deletes the clients (cascade) and the people the sheets created.
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import path from "node:path";

import { authAsRole, bearerFor } from "../../fixtures/multi-role-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const LOCAL_USER = process.env.E2E_LOCAL_USER;
const API_BASE = process.env.E2E_API_BASE ? `${process.env.E2E_API_BASE}/` : `${BASE}/api/`;
const authHeaders = (): Record<string, string> => (LOCAL_USER ? { "X-Test-User": LOCAL_USER } : bearerFor("system"));
const REPO = path.resolve(__dirname, "..", "..", "..", "..");
const SAMPLE = path.join(REPO, "docs/reference/DealGate_Cost_Margin_SAMPLE_StaffAug.xlsx");
const OWNER_COPY = path.join(REPO, "api/tests/forecast/fixtures/kanna_peppermill_v2.xlsx");
const RUN_TAG = `S22 e2e ${Date.now()}`;

let api: APIRequestContext;
const fixtureClients: string[] = [];
const engagementIds: string[] = [];

test.describe.configure({ mode: "serial" });
test.setTimeout(300_000);

async function issueFixture(label: string): Promise<string> {
  const issued = await api.post("dev/test-fixtures", { data: { label, reviewer_ids: [] } });
  if (!issued.ok()) throw new Error(`fixture issuer: ${issued.status()} ${await issued.text()}`);
  const id = ((await issued.json()) as { client_id: string }).client_id;
  fixtureClients.push(id);
  return id;
}

async function deleteClientAndWait(clientId: string): Promise<void> {
  const del = await api.delete(`clients/${clientId}`, { params: { reason: "S22 P4 upload teardown" } });
  if (!del.ok()) {
    console.warn(`[s22 p4 teardown] DELETE clients/${clientId} -> ${del.status()} ${await del.text()}`);
    return;
  }
  const body = (await del.json().catch(() => ({}))) as { job_id?: string };
  for (let attempt = 0; body.job_id && attempt < 60; attempt += 1) {
    const state = (await (await api.get(`deletion-jobs/${body.job_id}`)).json()) as { status: string };
    if (state.status === "done" || state.status === "failed") break;
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
}

test.beforeAll(async () => {
  api = await pwRequest.newContext({ baseURL: API_BASE, extraHTTPHeaders: authHeaders(), timeout: 90_000 });
});

test.afterAll(async () => {
  try {
    // people the sheets created (named by their role / name column) — collect before the cascade removes the links
    const peopleIds = new Set<string>();
    for (const id of engagementIds) {
      const rows = await api.get(`engagements/${id}/allocations`);
      if (rows.ok()) for (const r of (await rows.json()) as { resource_id: string }[]) peopleIds.add(r.resource_id);
    }
    for (const id of fixtureClients) await deleteClientAndWait(id);
    for (const id of peopleIds) await api.delete(`resources/${id}`).catch(() => undefined);
    const clients = (await (await api.get("clients?size=200")).json()) as { items?: { id: string; name: string }[] };
    for (const c of (clients.items ?? []).filter((x) => x.name.includes(RUN_TAG))) await deleteClientAndWait(c.id);
  } finally {
    await api.dispose();
  }
});

async function uploadOn(page: Page, file: string): Promise<string> {
  await page.goto(`${BASE}/engagements/new`);
  await expect(page.getByRole("heading", { name: "Upload the DealGate cost-margin sheet" })).toBeVisible();
  await page.getByLabel("Cost-margin sheet (.xlsx)").setInputFiles(file);
  await expect(page.getByTestId("import-note")).toContainText("Imported from the sheet.", { timeout: 120_000 });
  const id = page.url().match(/\/engagements\/([0-9a-f-]{36})/)?.[1] ?? "";
  expect(id).toBeTruthy();
  engagementIds.push(id);
  return id;
}

test("S22 P4-4 · the sample staff-aug sheet becomes an engagement with five people", async ({ page }) => {
  await issueFixture(`${RUN_TAG} Client A`);
  if (!LOCAL_USER) await authAsRole(page, "system");
  await uploadOn(page, SAMPLE);
  await expect(page.getByTestId("engagement-heading")).toContainText("STAFF AUG — Client A, 5 resources"); // the sheet's own project name
  await expect(page.getByTestId("status-line")).toContainText("PASS");
  await expect(page.getByTestId("allocation-row")).toHaveCount(5);
  const note = page.getByTestId("import-note");
  await expect(note).toContainText("matches the sheet");
  await note.getByRole("button", { name: "Dismiss" }).click();
  await expect(page.getByTestId("import-note")).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId("engagement-heading")).toBeVisible();
  await expect(page.getByTestId("import-note")).toHaveCount(0); // shown once
});

test("S22 P4-4 / P4-2 / P4-5 · the product owner's older copy imports with the hours check, short-term summary first", async ({ page }) => {
  await issueFixture(`${RUN_TAG} Peppermill`);
  if (!LOCAL_USER) await authAsRole(page, "system");
  const id = await uploadOn(page, OWNER_COPY);
  const note = page.getByTestId("import-note");
  await expect(note).toContainText("Sheet said 168 h for Vikrin");
  await expect(note).toContainText("the app computes 160 h");
  await expect(note).toContainText("2026-09-07");
  await expect(note).toContainText("Employment type");
  await expect(page.getByTestId("engagement-heading")).toContainText("Peppermill");
  await page.goto(`${BASE}/engagements/${id}/forecast`);
  await expect(page.getByTestId("monthly-required")).toContainText("Short engagement", { timeout: 60_000 });
  await expect(page.getByTestId("term-summary")).toBeVisible();
  await expect(page.getByRole("table", { name: "All resources by month" })).toHaveCount(0);
  await page.getByRole("button", { name: "Show month split" }).click();
  await expect(page.getByRole("table", { name: "All resources by month" })).toBeVisible();
  await expect(page.getByTestId("per-person-heading")).toHaveText("Per person · hours by month");
  await expect(page.getByRole("button", { name: "Hide month split" })).toBeVisible();
});
