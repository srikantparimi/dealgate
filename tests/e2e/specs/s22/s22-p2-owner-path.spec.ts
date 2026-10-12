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

/**
 * S21 runtime isolation: a test identity may only touch accounts the server
 * issued to it through POST /dev/test-fixtures (and DELETE /clients refuses
 * anything else). Locally, where the dev-seed endpoint is off, fall back to
 * POST /clients.
 */
async function issueFixtureClient(ctx: APIRequestContext, label: string): Promise<{ id: string; name: string; fixture: boolean }> {
  const issued = await ctx.post("dev/test-fixtures", { data: { label, reviewer_ids: [] } });
  if (issued.ok()) {
    const body = (await issued.json()) as { client_id: string; client_name?: string };
    const detail = await ctx.get(`clients/${body.client_id}`);
    const name = detail.ok() ? ((await detail.json()) as { name: string }).name : body.client_name ?? label;
    return { id: body.client_id, name, fixture: true };
  }
  const created = await ctx.post("clients", { data: { name: label } });
  if (!created.ok()) throw new Error(`${created.status()} creating client: ${await created.text()}`);
  const body = (await created.json()) as { id: string; name: string };
  return { id: body.id, name: body.name, fixture: false };
}

async function deleteClientAndWait(ctx: APIRequestContext, clientId: string, reason: string): Promise<boolean> {
  const del = await ctx.delete(`clients/${clientId}`, { params: { reason } });
  if (!del.ok()) {
    console.warn(`[s22 teardown] DELETE clients/${clientId} -> ${del.status()} ${await del.text()}`);
    return false;
  }
  const body = (await del.json().catch(() => ({}))) as { job_id?: string };
  for (let attempt = 0; body.job_id && attempt < 60; attempt += 1) {
    const state = (await (await ctx.get(`deletion-jobs/${body.job_id}`)).json()) as { status: string };
    if (state.status === "done" || state.status === "failed") break;
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
  return true;
}

let api: APIRequestContext;
let originalSettings: unknown = null;
let fixtureClient: { id: string; name: string; fixture: boolean } | null = null;

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
    // Order matters: the client delete cascades the engagement and its allocations; only then can people go.
    if (fixtureClient) await deleteClientAndWait(api, fixtureClient.id, "S22 P2 owner path teardown");
    const clients = (await (await api.get("clients?size=200")).json()) as { items?: { id: string; name: string }[] };
    for (const c of (clients.items ?? []).filter((x) => x.name.includes(RUN_TAG) && x.id !== fixtureClient?.id)) {
      await deleteClientAndWait(api, c.id, "S22 P2 owner path sweep");
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

  // 1 · New engagement. The account is server-issued (S21 runtime isolation) and picked from the Client
  // list; where the fixture issuer is off (local dev) the "+ New client…" path creates it from the form.
  fixtureClient = await issueFixtureClient(api, CLIENT_NAME).catch(() => null);
  const clientName = fixtureClient?.fixture ? fixtureClient.name : CLIENT_NAME;
  await page.goto(`${BASE}/engagements/new`);
  await expect(page.getByRole("heading", { name: "New engagement" })).toBeVisible();
  if (fixtureClient?.fixture) {
    await expect(page.getByLabel("Client *").locator(`option[value="${fixtureClient.id}"]`)).toHaveCount(1, { timeout: 60_000 });
    await page.getByLabel("Client *").selectOption(fixtureClient.id);
  } else {
    await page.getByLabel("Client *").selectOption("__new");
    await page.getByLabel("New client name").fill(CLIENT_NAME);
  }
  await page.getByLabel("Engagement name *").fill("Portal & data platform staffing");
  await page.getByLabel("Engagement type *").selectOption("staff_augmentation");
  await page.getByLabel("Start *").fill(iso(START));
  await page.getByLabel("End *").fill(iso(END));
  await page.getByLabel("Additional costs? *").selectOption("0");
  await page.getByLabel("Same start/end for everyone? *").selectOption("0");
  await page.getByRole("button", { name: "Create engagement" }).click();
  await expect(page.getByTestId("engagement-heading")).toHaveText(`${clientName} · Portal & data platform staffing`, { timeout: 60_000 });
  await expect(page.getByRole("tab", { name: "Allocations" })).toBeVisible();
  const engagementUrl = page.url();
  // Rule 18 / S21-12: the breadcrumb names the client and the engagement, never the UUID.
  const breadcrumb = page.getByRole("navigation", { name: /breadcrumb/i });
  await expect(breadcrumb).toContainText(clientName, { timeout: 60_000 });
  await expect(breadcrumb).toContainText("Portal & data platform staffing");
  // A server-issued fixture client is itself named around a run UUID; the check is on every other segment.
  const crumbText = (await breadcrumb.evaluate((el) => el.textContent ?? "")).split(clientName).join(""); // textContent: CSS capitalises innerText
  expect(crumbText).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}/i);
  expect(crumbText).not.toMatch(/\b[0-9a-f]{8}\b [0-9a-f]{4}\b/i);

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

  // 5b · Setup & costs: the project block is pre-filled; an additional cost is counted once the flag is Yes
  await page.getByRole("tab", { name: "Setup & costs" }).click();
  await expect(page.getByLabel("Engagement name", { exact: true })).toHaveValue("Portal & data platform staffing");
  await expect(page.getByLabel("Total price", { exact: true })).toBeDisabled(); // staff augmentation: no project price
  await expect(page.getByLabel("Monthly fee", { exact: true })).toBeDisabled();
  await page.getByRole("combobox", { name: "Additional costs", exact: true }).selectOption("1");
  await expect(page.getByRole("combobox", { name: "Additional costs", exact: true })).toHaveValue("1", { timeout: 60_000 });
  await page.getByRole("button", { name: "Add cost" }).click();
  const costDraft = page.getByTestId("cost-draft");
  await costDraft.getByLabel("New cost description", { exact: true }).fill("Kickoff travel");
  await costDraft.getByLabel("New cost amount", { exact: true }).fill("3200");
  await costDraft.getByLabel("New cost billed to client", { exact: true }).selectOption("1");
  await costDraft.getByRole("button", { name: "Add" }).click();
  await expect(page.getByTestId("cost-row")).toHaveCount(1, { timeout: 60_000 });
  await expect(page.getByLabel("Kickoff travel description", { exact: true })).toHaveValue("Kickoff travel");
  await expect(page.getByText(/Totals: \$3,200 cost, \$3,200 billed through/)).toBeVisible({ timeout: 60_000 });

  // 5c · Portfolio page: the engagement's row, the four cards, the totals row, the panels, CSV export
  await page.goto(`${BASE}/portfolio?month=${GAP_MONTH}`);
  await expect(page.getByRole("heading", { name: "Portfolio forecast" })).toBeVisible();
  await page.getByLabel("Client", { exact: true }).selectOption({ label: clientName });
  const row = page.getByRole("table", { name: "Portfolio forecast" }).locator("tbody tr").filter({ hasText: clientName });
  await expect(row).toHaveCount(1, { timeout: 60_000 });
  await expect(row).toContainText("Staff augmentation");
  await expect(row).toContainText(/PASS|BELOW FLOOR|INCOMPLETE/);
  for (const id of ["card-gm", "card-below_floor", "card-rolloffs", "card-bench"]) await expect(page.getByTestId(id)).toBeVisible();
  await expect(page.getByTestId("portfolio-totals")).toContainText(`Portfolio · ${monthLabel(GAP_MONTH)}`);
  await expect(page.getByRole("region", { name: "Roll-offs in the next 60 days" }).or(page.locator("#rolloffs"))).toBeVisible();
  await expect(page.locator("#bench")).toBeVisible();
  await expect(page.getByRole("button", { name: "Export CSV" })).toBeEnabled();
  const csv = await api.get("portfolio/forecast.csv", { params: { month: GAP_MONTH } });
  expect(csv.ok()).toBe(true);
  const csvText = await csv.text();
  expect(csvText.split("\n")[0]).toContain("Client,Engagement,Type");
  expect(csvText).toContain(clientName);
  expect(csvText).toContain(`Portfolio · ${GAP_MONTH}`);
  await page.goto(engagementUrl.replace(/\/allocations$/, "/forecast"));
  await expect(page.getByTestId("status-line")).toBeVisible();

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
