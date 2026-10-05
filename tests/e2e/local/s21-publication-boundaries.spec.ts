import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

const api = "http://127.0.0.1:8210";
function fixture() {
  if (!process.env.S21_PUB_MANIFEST) throw new Error("S21_PUB_MANIFEST requires an isolated fixture");
  const f = JSON.parse(readFileSync(process.env.S21_PUB_MANIFEST, "utf8"));
  expect(f.database).toMatch(/^s21_pub_[0-9a-f]{32}$/);
  return f;
}
function database(f: any, query: string) {
  return JSON.parse(execFileSync("docker", ["exec", "dealgate-s21-lead-db", "psql", "-U", "s21", "-d", f.database,
    "-At", "-v", "ON_ERROR_STOP=1", "-c", query], { encoding: "utf8", timeout: 20_000 }).trim());
}
const workforce = (f: any) => database(f, "SELECT json_build_object('intervals',(SELECT json_agg(t ORDER BY id) FROM workforce_interval t),'versions',(SELECT json_agg(t ORDER BY id) FROM workforce_version t))");
const counts = (f: any) => database(f, "SELECT json_build_object('publications',(SELECT count(*) FROM demand_publication_version),'drafts',(SELECT count(*) FROM sourcing_draft_version),'audits',(SELECT count(*) FROM audit_event),'intervals',(SELECT count(*) FROM workforce_interval),'versions',(SELECT count(*) FROM workforce_version))");

test("T23 admin source revision updates published demand and sourcing without reserving workforce", async ({ page, request }) => {
  test.setTimeout(180_000);
  const f = fixture();
  const headers = { "X-Test-User": f.actor_email };
  const persistedInputs = database(f, "SELECT json_agg(component_inputs) FROM forecast_plan_version");
  for (const sentinel of f.sentinels) expect(JSON.stringify(persistedInputs)).toContain(sentinel);
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const imported = await request.post(`${api}/people/imports`, { headers, data: { ...f.roster,
    request_key: crypto.randomUUID(), expected_previous_batch_id: null, reason: "Synthetic T23 managed capacity" } });
  expect(imported.status(), await imported.text()).toBe(201);
  const initialWorkforce = workforce(f);
  const forbidden = [{ reserve: true }, { hire: true }, { person_id: crypto.randomUUID() }, { status: "hired" }];
  for (const extra of forbidden) {
    const before = counts(f);
    const denied = await request.post(`${api}/people/demand/publications`, { headers, data: { ...f.publication_body, ...extra } });
    expect(denied.status(), await denied.text()).toBe(422);
    expect(counts(f)).toEqual(before);
    expect(workforce(f)).toEqual(initialWorkforce);
  }
  const publishedResponse = await request.post(`${api}/people/demand/publications`, { headers, data: f.publication_body });
  expect(publishedResponse.status(), await publishedResponse.text()).toBe(201);
  const published = await publishedResponse.json();
  const rulesResponse = await request.post(`${api}/people/sourcing/rules`, { headers, data: {
    rules: [{ skill: "python", location: "US", lead_days: 45 }, { skill: "python", location: "India", lead_days: 30 }],
    expected_version_id: null, request_key: crypto.randomUUID(), reason: "Explicit synthetic regional sourcing rules" } });
  expect(rulesResponse.status(), await rulesResponse.text()).toBe(201);
  const rules = await rulesResponse.json();
  const draftBody = { publication_id: published.publication_id, expected_demand_version_id: published.version_id,
    expected_rule_version_id: rules.id, expected_draft_version_id: null, request_key: crypto.randomUUID(), reason: "Original source before revision" };
  for (const extra of forbidden) {
    const before = counts(f);
    const denied = await request.post(`${api}/people/sourcing/drafts`, { headers, data: { ...draftBody, ...extra } });
    expect(denied.status(), await denied.text()).toBe(422);
    expect(counts(f)).toEqual(before);
    expect(workforce(f)).toEqual(initialWorkforce);
  }
  const firstResponse = await request.post(`${api}/people/sourcing/drafts`, { headers, data: draftBody });
  expect(firstResponse.status(), await firstResponse.text()).toBe(201);
  const first = await firstResponse.json();
  expect(first.is_reservation).toBe(false);
  expect(first.snapshot.complete).toBe(true);
  for (const [location, quantity] of [["US", 2], ["India", 5]] as const) {
    const rows = first.snapshot.rows.filter((r: any) => r.location === location);
    expect(rows.map((r: any) => r.start)).toEqual(["2026-11-01", "2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01"]);
    expect(rows.at(-1).end_exclusive).toBe("2027-05-01");
    for (const row of rows) {
      expect(row.quantity).toBe(quantity);
      expect(Number(row.gap_fte)).toBe(0.5);
    }
  }
  expect(workforce(f)).toEqual(initialWorkforce);
  for (const path of ["/people/reservations", "/people/hire"]) {
    const before = counts(f);
    const missing = await request.post(`${api}${path}`, { headers, data: { person_id: crypto.randomUUID() } });
    expect([404, 405]).toContain(missing.status());
    expect(counts(f)).toEqual(before);
  }
  const oldPublication = database(f, "SELECT json_agg(t ORDER BY id) FROM demand_publication_version t");
  const oldLines = database(f, "SELECT json_agg(t ORDER BY id) FROM demand_line t");
  const revisedResponse = await request.post(`${api}/forecast/plans/${f.plan_id}/versions`, { headers, data: f.revision_body });
  expect(revisedResponse.status(), await revisedResponse.text()).toBe(201);
  const revision = await revisedResponse.json();
  expect(revision.version).toBe(2);
  await page.goto("/people/demand");
  const source = page.getByRole("region", { name: f.title, exact: true });
  await expect(source).toContainText("stale");
  const staleDraft = await request.post(`${api}/people/sourcing/drafts`, { headers, data: { ...draftBody,
    expected_draft_version_id: first.id, request_key: crypto.randomUUID() } });
  expect(staleDraft.status(), await staleDraft.text()).toBe(409);
  await source.getByRole("button", { name: "Publish demand", exact: true }).click();
  await source.getByRole("textbox", { name: "Publication reason", exact: true }).fill("Publish changed dates and eight half-time slots");
  await source.getByRole("button", { name: "Publish latest source", exact: true }).click();
  await expect(source).not.toContainText("stale");
  await expect(source.getByRole("row").filter({ hasText: "America/New_York" }).getByRole("cell").nth(2)).toHaveText("3");
  await page.reload();
  await expect(source).toContainText("2026-12-01");
  const allocationResponse = await request.get(`${api}/people/demand/allocation?account_id=${f.account_id}`, { headers });
  expect(allocationResponse.status()).toBe(200);
  const allocation = await allocationResponse.json();
  expect(allocation.complete).toBe(true);
  expect(allocation.months.map((m: any) => m.month)).toEqual(["2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01"]);
  for (const month of allocation.months) {
    expect(month.peak_headcount).toBe(8);
    expect(Number(month.peak_fte)).toBe(4);
    expect(Number(month.gap_fte)).toBe(1.5);
  }
  await page.goto("/people/sourcing");
  await page.getByLabel("Published source", { exact: true }).selectOption(f.plan_id);
  await expect(page.getByText("Draft state: stale", { exact: true })).toBeVisible();
  await page.getByLabel("Draft reason", { exact: true }).fill("Changed dates and headcount source revision");
  await page.getByRole("button", { name: "Prepare sourcing draft", exact: true }).click();
  await expect(page.getByText("Sourcing draft revision 2 prepared", { exact: true })).toBeVisible();
  await page.reload();
  await page.getByLabel("Published source", { exact: true }).selectOption(f.plan_id);
  const draft = page.getByRole("article");
  await expect(draft).toContainText("Changed dates and headcount source revision");
  for (const [zone, quantity, gap, fte, date] of [["America/New_York", "3", "2", "1", "2026-10-17"], ["Asia/Kolkata", "5", "1", "0.5", "2026-11-01"]]) {
    const rows = draft.getByRole("row").filter({ hasText: zone });
    await expect(rows).toHaveCount(5);
    for (const row of await rows.all()) {
      const cells = row.getByRole("cell");
      await expect(cells.nth(2)).toHaveText(quantity);
      await expect(cells.nth(6)).toHaveText(gap);
      expect(Number(await cells.nth(9).textContent())).toBe(Number(fte));
      await expect(cells.nth(10)).toHaveText(date);
    }
  }
  const historyResponse = await request.get(`${api}/people/sourcing/drafts?publication_id=${published.publication_id}`, { headers });
  expect(historyResponse.status()).toBe(200);
  const history = await historyResponse.json();
  expect(history.items.map((d: any) => d.revision)).toEqual([2, 1]);
  expect(history.items[1]).toEqual(first);
  expect(history.items[0].snapshot.source_version_id).toBe(revision.version_id);
  const allPublications = database(f, "SELECT json_agg(t ORDER BY id) FROM demand_publication_version t");
  expect(allPublications).toContainEqual(oldPublication[0]);
  const allLines = database(f, "SELECT json_agg(t ORDER BY id) FROM demand_line t");
  for (const line of oldLines) expect(allLines).toContainEqual(line);
  expect(workforce(f)).toEqual(initialWorkforce);
  writeFileSync(`${process.env.S21_PUB_MANIFEST}.proof.json`, JSON.stringify({ publication_id: published.publication_id,
    allocation, history, beforeWorkforce: initialWorkforce, sourceRevision: revision }, null, 2));
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t23-publication.png", fullPage: true });
});

test("T23 Sales-only reader gets owned demand without costs or named workforce", async ({ page, request }) => {
  const f = fixture();
  const headers = { "X-Test-User": f.actor_email };
  const me = await request.get(`${api}/me`, { headers });
  expect((await me.json()).groups).toEqual(["Sales", "officeapp-e2e"]);
  const forbidden = new Set([...f.financial_sentinels.forbidden_fields, "revenue", "margin", "inputs", "component_inputs", "matches", "retained_person_ids"]);
  function costFree(value: any) {
    if (!value || typeof value !== "object") return;
    for (const [key, child] of Object.entries(value)) {
      expect(forbidden.has(key), `Forbidden field ${key}`).toBe(false);
      costFree(child);
    }
    for (const sentinel of f.sentinels) expect(JSON.stringify(value)).not.toContain(sentinel);
  }
  for (const path of ["/people/demand", `/people/demand/allocation?account_id=${f.account_id}`]) {
    const response = await request.get(`${api}${path}`, { headers });
    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(JSON.stringify(data)).toContain(f.plan_id);
    if (path === "/people/demand") {
      const owned = data.items.find((s: any) => s.plan_id === f.plan_id);
      expect(owned.state).toBe("current");
      expect(owned.lines.map((l: any) => l.quantity).sort()).toEqual([3, 5]);
    } else {
      expect(data.complete).toBe(true);
      expect(data.months.map((m: any) => m.month)).toEqual(["2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01"]);
      for (const month of data.months) {
        expect(month.peak_headcount).toBe(8);
        expect(Number(month.peak_fte)).toBe(4);
        expect(Number(month.gap_fte)).toBe(1.5);
      }
      expect(data.intervals).toHaveLength(5);
      for (const interval of data.intervals) expect(interval.demands).toHaveLength(2);
    }
    costFree(data);
  }
  for (const path of ["/people/availability", "/people/imports", "/people/sourcing/rules"]) {
    expect((await request.get(`${api}${path}`, { headers })).status()).toBe(403);
  }
  const proof = JSON.parse(readFileSync(`${process.env.S21_PUB_MANIFEST}.proof.json`, "utf8"));
  expect((await request.get(`${api}/people/sourcing/drafts?publication_id=${proof.publication_id}`, { headers })).status()).toBe(403);
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  await page.goto("/people/demand");
  const source = page.getByRole("region", { name: f.title, exact: true });
  await expect(source).toBeVisible();
  await expect(source).toContainText("2026-12-01");
  await expect(source.getByRole("button", { name: /Publish|Revise|Reserve|Hire/ })).toHaveCount(0);
  const content = await source.textContent();
  for (const sentinel of f.sentinels) expect(content).not.toContain(sentinel);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t23-sales-demand.png", fullPage: true });
});
