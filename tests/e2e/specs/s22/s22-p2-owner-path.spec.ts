/**
 * S22 P2-6 · the product owner's path, on the deployed SPA.
 *
 *   new engagement → five people → one leaves → re-hire → Forecast shows the
 *   gap month at zero → Settings change to burden moves the numbers.
 *
 * Asserts on what the owner sees (headings, tabs, buttons, cells), rule 18.
 * Everything is real: Cognito, CloudFront, the API, RDS, the engine. The
 * client is created under an S22 run tag and torn down in afterAll with the
 * people it created, so the leak gate reads 0.
 *
 *   E2E_BASE_URL=https://app.dealgateapp.com npx playwright test specs/s22/s22-p2-owner-path.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";

import { authAsRole, bearerFor } from "../../fixtures/multi-role-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
// Local full-stack runs (uvicorn + Vite, DEALGATE_ENV=local): identity comes from the
// X-Test-User header / VITE_TEST_USER instead of Cognito. Unset on staging.
const LOCAL_USER = process.env.E2E_LOCAL_USER;
const API_BASE = process.env.E2E_API_BASE ? `${process.env.E2E_API_BASE}/` : `${BASE}/api/`;
const authHeaders = (): Record<string, string> => (LOCAL_USER ? { "X-Test-User": LOCAL_USER } : bearerFor("system"));
const RUN_TAG = `S22 e2e ${Date.now()}`;
const CLIENT_NAME = `${RUN_TAG} Client`;

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}
function monthKey(d: Date): string {
  return iso(d).slice(0, 7);
}
function utc(year: number, monthIndex: number, day: number): Date {
  return new Date(Date.UTC(year, monthIndex, day));
}
function monthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}

// A running engagement: started last month, ends in six months, so "Leaves"
// (end = last day of this month) and a re-hire two months out produce a gap.
const now = new Date();
const START = utc(now.getUTCFullYear(), now.getUTCMonth() - 1, 1);
const END = utc(now.getUTCFullYear(), now.getUTCMonth() + 7, 0);
const GAP_MONTH = monthKey(utc(now.getUTCFullYear(), now.getUTCMonth() + 1, 1));
const REHIRE_START = utc(now.getUTCFullYear(), now.getUTCMonth() + 2, 1);

const PEOPLE = [
  { name: `${RUN_TAG} Dev US`, role: "Developer", location: "US", employment: "w2_employee", bill: "135", cost: "70", assignment: "Portal rebuild" },
  { name: `${RUN_TAG} Tester US`, role: "Tester", location: "US", employment: "contractor_1099", bill: "95", cost: "55", assignment: "Portal rebuild" },
  { name: `${RUN_TAG} Architect US`, role: "Architect", location: "US", employment: "contractor_1099", bill: "185", cost: "120", assignment: "Data platform" },
  { name: `${RUN_TAG} Dev IN 1`, role: "Developer", location: "India", employment: "w2_employee", bill: "48", cost: "20", assignment: "Data platform" },
  { name: `${RUN_TAG} Dev IN 2`, role: "Developer", location: "India", employment: "w2_employee", bill: "48", cost: "22", assignment: "Data platform" },
];

let api: APIRequestContext;
let originalSettings: unknown = null;

test.describe.configure({ mode: "serial" });
// Six screens and ten server round-trips: longer than the 30 s local default.
test.setTimeout(300_000);

test.beforeAll(async () => {
  api = await pwRequest.newContext({ baseURL: API_BASE, extraHTTPHeaders: authHeaders(), timeout: 90_000 });
  const settings = await api.get("settings/forecast");
  if (settings.ok()) originalSettings = await settings.json();
});

test.afterAll(async () => {
  try {
    if (originalSettings) {
      // Put the calendar back exactly as it was before the burden change.
      await api.put("settings/forecast", { data: originalSettings }).catch(() => undefined);
    }
    const clients = (await (await api.get("clients?size=200")).json()) as { items?: { id: string; name: string }[] };
    for (const c of (clients.items ?? []).filter((x) => x.name.includes(RUN_TAG))) {
      const del = await api.delete(`clients/${c.id}`, { params: { reason: "S22 P2 owner path teardown" } });
      if (del.ok()) {
        const body = (await del.json().catch(() => ({}))) as { job_id?: string };
        for (let attempt = 0; body.job_id && attempt < 60; attempt += 1) {
          const state = (await (await api.get(`deletion-jobs/${body.job_id}`)).json()) as { status: string };
          if (state.status === "done" || state.status === "failed") break;
          await new Promise((resolve) => setTimeout(resolve, 2_000));
        }
      }
    }
    const people = (await (await api.get("resources")).json()) as { id: string; name: string }[];
    for (const p of people.filter((r) => r.name.includes(RUN_TAG))) await api.delete(`resources/${p.id}`).catch(() => undefined);
  } finally {
    await api.dispose();
  }
});

async function addPerson(page: Page, person: (typeof PEOPLE)[number]) {
  await page.getByRole("button", { name: "Add person" }).click();
  const draft = page.getByTestId("draft-row");
  await expect(draft).toBeVisible();
  await draft.getByLabel("Person", { exact: true }).selectOption("");
  await draft.getByLabel("New person name", { exact: true }).fill(person.name);
  await draft.getByLabel("Role", { exact: true }).fill(person.role);
  await draft.getByLabel("Location", { exact: true }).selectOption(person.location);
  await draft.getByLabel("Employment type", { exact: true }).selectOption(person.employment);
  await draft.getByLabel("Assignment", { exact: true }).fill(person.assignment);
  await draft.getByLabel("Bill rate", { exact: true }).fill(person.bill);
  await draft.getByLabel("Our cost per hour", { exact: true }).fill(person.cost);
  await draft.getByRole("button", { name: "Add" }).click();
  await expect(page.getByTestId("allocation-row").filter({ hasText: person.name })).toBeVisible({ timeout: 60_000 });
}

test("S22 P2-6 · owner path: new engagement → five people → leaves → re-hire → gap month at zero → burden moves the numbers", async ({ page }) => {
  if (!LOCAL_USER) await authAsRole(page, "system");

  // 1 · New engagement with a new client
  await page.goto(`${BASE}/engagements/new`);
  await expect(page.getByRole("heading", { name: "New engagement" })).toBeVisible();
  await page.getByLabel("Client *").selectOption("__new");
  await page.getByLabel("New client name").fill(CLIENT_NAME);
  await page.getByLabel("Engagement name *").fill("Portal & data platform staffing");
  await page.getByLabel("Engagement type *").selectOption("staff_augmentation");
  await page.getByLabel("Start *").fill(iso(START));
  await page.getByLabel("End *").fill(iso(END));
  await page.getByLabel("Additional costs? *").selectOption("0");
  await page.getByLabel("Same start/end for everyone? *").selectOption("0");
  await page.getByRole("button", { name: "Create engagement" }).click();
  await expect(page.getByTestId("engagement-heading")).toHaveText(`${CLIENT_NAME} · Portal & data platform staffing`, { timeout: 60_000 });
  await expect(page.getByRole("tab", { name: "Allocations" })).toBeVisible();
  const engagementUrl = page.url();
  // Rule 18 / S21-12: the breadcrumb names the client and the engagement, never the UUID.
  const breadcrumb = page.getByRole("navigation", { name: /breadcrumb/i });
  await expect(breadcrumb).toContainText(CLIENT_NAME, { timeout: 60_000 });
  await expect(breadcrumb).toContainText("Portal & data platform staffing");
  await expect(breadcrumb).not.toContainText(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}/i);
  await expect(breadcrumb).not.toContainText(/\b[0-9a-f]{8}\b [0-9a-f]{4}\b/i);

  // 2 · Five people
  for (const person of PEOPLE) await addPerson(page, person);
  await expect(page.getByTestId("allocation-row")).toHaveCount(5);
  await expect(page.getByTestId("status-line")).toContainText("PASS");

  // 3 · One leaves (end = last day of this month)
  const tester = page.getByTestId("allocation-row").filter({ hasText: PEOPLE[1].name });
  await tester.getByRole("button", { name: "Leaves" }).click();
  const thisMonthEnd = iso(utc(now.getUTCFullYear(), now.getUTCMonth() + 1, 0));
  await expect(tester.getByLabel(`${PEOPLE[1].name} end`, { exact: true })).toHaveValue(thisMonthEnd, { timeout: 60_000 });

  // 4 · Re-hire (new row from the day after), then push its start two months out → a gap month
  await tester.getByRole("button", { name: "Re-hire" }).click();
  await expect(page.getByTestId("allocation-row").filter({ hasText: PEOPLE[1].name })).toHaveCount(2, { timeout: 60_000 });
  const rehired = page.getByTestId("allocation-row").filter({ hasText: PEOPLE[1].name }).nth(1);
  await rehired.getByLabel(`${PEOPLE[1].name} start`, { exact: true }).fill(iso(REHIRE_START));
  await rehired.getByLabel(`${PEOPLE[1].name} start`, { exact: true }).blur();
  await expect(rehired.getByLabel(`${PEOPLE[1].name} start`, { exact: true })).toHaveValue(iso(REHIRE_START), { timeout: 60_000 });

  // 5 · Forecast shows the gap month at zero for that person (blank cell = nobody billing)
  await page.getByRole("tab", { name: "Forecast" }).click();
  await expect(page.getByTestId("monthly-required")).toContainText("Monthly view required");
  const perPerson = page.getByRole("table", { name: /Per person/ }).first();
  const headers = await perPerson.locator("thead th").allInnerTexts();
  const gapIndex = headers.findIndex((h) => h.trim().toLowerCase() === monthLabel(GAP_MONTH).toLowerCase()); // headers render uppercase via CSS
  expect(gapIndex, `month ${GAP_MONTH} is a column`).toBeGreaterThan(0);
  const testerRows = perPerson.locator("tbody tr").filter({ hasText: PEOPLE[1].name });
  await expect(testerRows).toHaveCount(2);
  for (const row of await testerRows.all()) {
    await expect(row.locator("td").nth(gapIndex)).toHaveText("");
  }
  const costBefore = (await page.getByTestId("status-line").innerText()).match(/cost (\$[\d,]+)/)?.[1];
  expect(costBefore).toBeTruthy();

  // 6 · Settings change to burden moves the numbers
  await page.goto(`${BASE}/settings/forecast`);
  await expect(page.getByRole("heading", { name: "Forecast calendar" })).toBeVisible();
  const usBurden = page.getByLabel("US burden W-2 %", { exact: true });
  const before = await usBurden.inputValue();
  await usBurden.fill(String(Number(before) + 10));
  await page.getByRole("button", { name: "Save calendar" }).click();
  await expect(page.getByRole("status")).toContainText("Forecast calendar saved", { timeout: 60_000 });

  await page.goto(engagementUrl.replace(/\/allocations$/, "/forecast"));
  await expect(page.getByTestId("status-line")).toBeVisible();
  await expect
    .poll(async () => (await page.getByTestId("status-line").innerText()).match(/cost (\$[\d,]+)/)?.[1], { timeout: 60_000 })
    .not.toBe(costBefore);
});
