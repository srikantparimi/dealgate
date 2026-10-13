/**
 * S22 P5-8 · the product owner's path, on the deployed SPA:
 *
 *   /import/forecast-model → upload the synthetic forecast-model fixture → dry run shows the three business
 *   units → Load → lands on /portfolio → /portfolio/it-avalon shows Gamma Health-VMS → its Forecast tab shows
 *   the Actuals block → /portfolio shows three subtotal rows (one per BU) that add to the grand total.
 *
 * The fixture is the synthetic workbook api/tests/forecast/test_forecast_model_import.py generates (invented
 * people and clients; the real model never enters the repo). Its clients are server-issued fixture accounts
 * named after the sheet's clients (S21 runtime isolation). Retro Rabbit has no client tab in the fixture, so
 * one Retro Rabbit engagement is created through the API to make the third subtotal real.
 * Teardown: clients (cascade), the people the model created, and the calendar restored to its snapshot
 * (the import adds the model's locations + holidays; on staging those must not outlive the test).
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import path from "node:path";

import { authAsRole, bearerFor } from "../../fixtures/multi-role-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const LOCAL_USER = process.env.E2E_LOCAL_USER;
const API_BASE = process.env.E2E_API_BASE ? `${process.env.E2E_API_BASE}/` : `${BASE}/api/`;
const authHeaders = (): Record<string, string> => (LOCAL_USER ? { "X-Test-User": LOCAL_USER } : bearerFor("system"));
const REPO = path.resolve(__dirname, "..", "..", "..", "..");
const MODEL = path.join(REPO, "api/tests/forecast/fixtures/forecast_model_synthetic_complete.xlsx"); // P5c: the full fixture carries a blocking tab; the owner path loads the complete copy
const RUN_TAG = `S22 e2e ${Date.now()}`;
const MONTH = "2026-02"; // both Gamma engagements are active and carry actuals; Alpha + Beta (ST21) are active
const MODEL_CLIENTS = ["Alpha Retail", "Beta Insurance", "Gamma Health-VMS", "Delta Closed"];

let api: APIRequestContext;
let calendarBefore: unknown;
const fixtureClients: string[] = [];

test.describe.configure({ mode: "serial" });
test.setTimeout(300_000);

const money = (text: string | null): number => Number((text ?? "").replace(/[^0-9.-]/g, "") || "0");

async function issueFixture(label: string): Promise<string> {
  const issued = await api.post("dev/test-fixtures", { data: { label, reviewer_ids: [] } });
  if (!issued.ok()) throw new Error(`fixture issuer: ${issued.status()} ${await issued.text()}`);
  const id = ((await issued.json()) as { client_id: string }).client_id;
  fixtureClients.push(id);
  return id;
}

async function deleteClientAndWait(clientId: string): Promise<void> {
  const del = await api.delete(`clients/${clientId}`, { params: { reason: "S22 P5 teardown" } });
  if (!del.ok()) {
    console.warn(`[s22 p5 teardown] DELETE clients/${clientId} -> ${del.status()} ${await del.text()}`);
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
  api = await pwRequest.newContext({ baseURL: API_BASE, extraHTTPHeaders: authHeaders(), timeout: 120_000 });
  calendarBefore = await (await api.get("settings/forecast")).json();
  for (const name of MODEL_CLIENTS) await issueFixture(`${RUN_TAG} ${name}`);
  // the third business unit: one Retro Rabbit engagement with one person, through the API
  const rrClient = await issueFixture(`${RUN_TAG} Client RR`);
  const eng = await (await api.post("engagements", { data: {
    client_id: rrClient, name: "Tracker support (T&M, SA)", type: "time_and_materials", start: "2026-01-01", end: "2026-12-31",
    additional_costs_flag: false, same_dates_for_all: true, business_unit: "Retro Rabbit", sales_owner: "Jo Smith", delivery_owner: "Jo Smith",
  } })).json() as { id: string };
  const person = await (await api.post("resources", { data: { name: `${RUN_TAG} Lead Developer`, location: "US", employment_type: "contractor_1099", seniority: "Mid" } })).json() as { id: string };
  const alloc = await api.post(`engagements/${eng.id}/allocations`, { data: { resource_id: person.id, role: "Lead Developer", utilization: 1, bill_rate: 69, cost_per_hour: 45, rate_basis: "hourly", person: "Jo Dev" } });
  if (!alloc.ok()) throw new Error(`Retro Rabbit allocation: ${alloc.status()} ${await alloc.text()}`);
});

test.afterAll(async () => {
  try {
    const peopleIds = new Set<string>();
    const clients = (await (await api.get("clients?size=200")).json()) as { items?: { id: string; name: string }[] };
    const mine = (clients.items ?? []).filter((c) => c.name.includes(RUN_TAG)).map((c) => c.id);
    for (const id of new Set([...fixtureClients, ...mine])) {
      const engs = (await (await api.get(`engagements?client_id=${id}&page_size=50`)).json()) as { items?: { id: string }[] };
      for (const e of engs.items ?? []) {
        const rows = await api.get(`engagements/${e.id}/allocations`);
        if (rows.ok()) for (const r of (await rows.json()) as { resource_id: string }[]) peopleIds.add(r.resource_id);
      }
    }
    for (const id of new Set([...fixtureClients, ...mine])) await deleteClientAndWait(id);
    for (const id of peopleIds) await api.delete(`resources/${id}`).catch(() => undefined);
    const stray = (await (await api.get("resources")).json()) as { id: string; name: string }[];
    for (const r of stray.filter((x) => x.name.includes(RUN_TAG))) await api.delete(`resources/${r.id}`).catch(() => undefined);
    if (calendarBefore) {
      const restored = await api.put("settings/forecast", { data: calendarBefore });
      if (!restored.ok()) console.warn(`[s22 p5 teardown] calendar restore -> ${restored.status()} ${await restored.text()}`);
    }
  } finally {
    await api.dispose();
  }
});

async function openAs(page: Page): Promise<void> {
  if (!LOCAL_USER) await authAsRole(page, "system");
}

test("S22 P5-8 · upload the model → dry run (3 BUs) → load → lands on /portfolio", async ({ page }) => {
  await openAs(page);
  await page.goto(`${BASE}/import/forecast-model`);
  await expect(page.getByRole("heading", { name: "Import the forecast model" })).toBeVisible();
  await page.getByLabel("Forecast model (.xlsx)").setInputFiles(MODEL);
  const cards = page.getByTestId("dry-run-cards");
  await expect(cards).toBeVisible({ timeout: 120_000 });
  const bus = await cards.getByTestId("dry-run-card").evaluateAll((els) => els.map((e) => e.getAttribute("data-bu")));
  expect(bus).toEqual(expect.arrayContaining(["ST21", "IT Avalon", "Retro Rabbit"]));
  await expect(page.getByTestId("dry-run-tabs")).toContainText("Gamma Health-VMS");
  await expect(page.getByTestId("dry-run-report")).toContainText("By business unit");
  await page.getByRole("button", { name: /^Load / }).click();
  await expect(page).toHaveURL(/\/portfolio(\?.*)?$/, { timeout: 180_000 });
});

test("S22 P5-8 · /portfolio/it-avalon shows Gamma Health-VMS; its Forecast tab shows the Actuals block", async ({ page }) => {
  await openAs(page);
  await page.goto(`${BASE}/portfolio/it-avalon?month=${MONTH}`);
  await expect(page.getByTestId("bu-tabs")).toBeVisible();
  await expect(page.getByRole("heading", { name: /IT Avalon forecast/ })).toBeVisible();
  const row = page.getByTestId("portfolio-row").filter({ hasText: "Gamma Health-VMS" }).first();
  await expect(row).toBeVisible({ timeout: 60_000 });
  await expect(row.getByTestId("row-owners")).toContainText("Kim");
  await expect(page.getByTestId("bu-subtotal")).toHaveCount(1);
  await expect(page.getByTestId("bu-subtotal").first()).toHaveAttribute("data-bu", "IT Avalon");
  await row.click();
  await expect(page).toHaveURL(/\/engagements\/[0-9a-f-]{36}/);
  const id = page.url().match(/\/engagements\/([0-9a-f-]{36})/)?.[1] ?? "";
  await page.goto(`${BASE}/engagements/${id}/forecast`);
  const actuals = page.getByTestId("actuals-block");
  await expect(actuals).toBeVisible({ timeout: 60_000 });
  await expect(actuals).toContainText("Billed");
  await expect(actuals).toContainText("Billing loss");
});

test("S22 P5-8 / P5-9 · /portfolio shows three subtotal rows that add to the grand total", async ({ page }) => {
  await openAs(page);
  await page.goto(`${BASE}/portfolio?month=${MONTH}`);
  await expect(page.getByTestId("bu-tabs")).toBeVisible();
  const subtotals = page.getByTestId("bu-subtotal");
  await expect(subtotals).toHaveCount(3, { timeout: 60_000 });
  const bus = await subtotals.evaluateAll((els) => els.map((e) => e.getAttribute("data-bu")));
  expect(bus).toEqual(["ST21", "IT Avalon", "Retro Rabbit"]);
  await expect(page.getByTestId("bu-group")).toHaveCount(3);
  const revenues = await subtotals.getByTestId("subtotal-revenue").allTextContents();
  const total = money(await page.getByTestId("portfolio-total").getByTestId("total-revenue").textContent());
  const sum = revenues.map(money).reduce((a, b) => a + b, 0);
  expect(Math.abs(sum - total)).toBeLessThanOrEqual(0.011);
  await expect(page.getByTestId("card-billing-loss")).toContainText("engagements with actuals");
  // closed engagements are off the page
  await expect(page.getByTestId("portfolio-row").filter({ hasText: "Delta Closed" })).toHaveCount(0);
});
