import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("Company X demand publishes to People and retains seven people after probability revision", async ({ page, request }) => {
  test.setTimeout(180_000);
  const headers = { "X-Test-User": "s21-browser@example.test" };
  const base = "http://127.0.0.1:8210";
  const fixtureResponse = await request.post(`${base}/dev/test-fixtures`, { headers,
    data: { label: "Company X demand browser", reviewer_ids: [], hours: 4 } });
  expect(fixtureResponse.status()).toBe(201);
  const fixture = await fixtureResponse.json();
  const api = resolve(process.cwd(), "../../api");
  const inputs = JSON.parse(execFileSync(resolve(api, ".venv/bin/python"), ["-c", `
import json
from dataclasses import replace
from decimal import Decimal
from app.gm.commercial import HybridPricing
from app.services.commercial_models import COMPONENT
from tests.test_s21_commercial_profiles import component, staffing
us = staffing(component_id="us", assignment_id="us-team", quantity=2, allocation=Decimal("1"))
india = staffing(component_id="india", assignment_id="india-team", quantity=5, allocation=Decimal("1"), location="India",
    timezone="Asia/Kolkata", calendar=replace(us.calendar, timezone="Asia/Kolkata"))
us_part = component(component_id="us", staffing=(us,), costs=())
us_part = replace(us_part, pricing=replace(us_part.pricing,
    allocations=tuple(replace(row, location="US") for row in us_part.pricing.allocations)))
india_part = component(component_id="india", timezone="Asia/Kolkata", staffing=(india,), costs=())
root = component(profile="hybrid", pricing=HybridPricing((us_part, india_part)), costs=())
print(json.dumps(COMPONENT.dump_python(root, mode="json")))
`], { cwd: api, encoding: "utf8", timeout: 20_000 }));
  const title = `Synthetic Company X demand ${crypto.randomUUID()}`;
  const planResponse = await request.post(`${base}/forecast/plans`, { headers, data: {
    account_id: fixture.client_id, opportunity_id: fixture.opportunity_id, title,
    idempotency_key: crypto.randomUUID(), inputs, probability: "0.70",
    probability_source: "Synthetic assessment supports seven-person team",
    assumptions: ["Two US and five India engineers; full dated staffing"], change_reason: "Connected demand proof",
  } });
  expect(planResponse.status()).toBe(201);
  const plan = await planResponse.json();
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  async function sourcing(initial: boolean) {
    await page.goto("/people/sourcing");
    await expect(page.getByRole("button", { name: "Add rule", exact: true })).toBeEnabled();
    if (initial) {
      while (await page.getByRole("button", { name: /^Remove rule \d+$/ }).count()) {
        await page.getByRole("button", { name: /^Remove rule \d+$/ }).first().click();
      }
      for (const [index, location, days] of [[1, "US", "45"], [2, "India", "30"]] as const) {
        await page.getByRole("button", { name: "Add rule", exact: true }).click();
        await page.getByLabel(`Skill ${index}`, { exact: true }).fill("python");
        await page.getByLabel(`Location ${index}`, { exact: true }).fill(location);
        await page.getByLabel(`Lead days ${index}`, { exact: true }).fill(days);
      }
      await page.getByLabel("Rule change reason", { exact: true }).fill("Synthetic HR approves regional lead times");
      await page.getByRole("button", { name: "Save rules", exact: true }).click();
      await expect(page.getByText(/Rules revision \d+ saved/)).toBeVisible();
    }
    await page.getByLabel("Published source", { exact: true }).selectOption(plan.id);
    await page.getByLabel("Draft reason", { exact: true }).fill(initial ? "Initial seven-person sourcing review" : "Revised probability, unchanged full team");
    await page.getByRole("button", { name: "Prepare sourcing draft", exact: true }).click();
    await expect(page.getByText(`Sourcing draft revision ${initial ? 1 : 2} prepared`, { exact: true })).toBeVisible();
    const draft = page.getByRole("article");
    await expect(draft).toContainText(`Win probability: ${initial ? "70.0%" : "40.0%"}`);
    for (const [zone, count, deadline] of [["America/New_York", "2", "2026-09-17"], ["Asia/Kolkata", "5", "2026-10-02"]]) {
      const rows = draft.getByRole("row").filter({ hasText: zone });
      await expect(rows.first()).toBeVisible();
      for (const row of await rows.all()) {
        await expect(row.getByRole("cell").nth(2)).toHaveText(count);
        await expect(row.getByRole("cell").nth(10)).toHaveText(deadline);
      }
    }
    await page.reload();
    await expect(page.getByRole("button", { name: "Add rule", exact: true })).toBeEnabled();
    await page.getByLabel("Published source", { exact: true }).selectOption(plan.id);
    await expect(page.getByRole("article")).toContainText(initial ? "Initial seven-person sourcing review" : "Revised probability, unchanged full team");
  }
  const url = `/forecast?view=resources&account_id=${fixture.client_id}&as_of=2026-10-01T12:00:00Z`;
  await page.goto(url);
  await expect(page.getByRole("tab", { name: "Resource demand", exact: true })).toHaveAttribute("aria-selected", "true");
  const source = page.getByRole("region", { name: title, exact: true });
  await source.getByRole("button", { name: "Publish demand", exact: true }).click();
  await source.getByRole("textbox", { name: "Publication reason", exact: true }).fill("Publish full source staffing to People");
  await source.getByRole("button", { name: "Publish latest source", exact: true }).click();
  await expect(source).toContainText("Skills unknown");
  await source.getByRole("button", { name: "Revise demand", exact: true }).click();
  for (const location of ["US", "India"]) {
    const group = source.getByRole("group", { name: new RegExp(`Engineer.*${location}`) });
    await group.getByRole("textbox", { name: "Skills for Engineer", exact: true }).fill("python");
    await group.getByRole("textbox", { name: "Level for Engineer", exact: true }).fill("senior");
    await group.getByRole("textbox", { name: "Evidence for Engineer", exact: true }).fill(`Synthetic HR confirms ${location} skill and level`);
  }
  await source.getByRole("textbox", { name: "Publication reason", exact: true }).fill("Confirm capability without changing source headcount");
  await source.getByRole("button", { name: "Publish latest source", exact: true }).click();
  await expect(source).not.toContainText("Skills unknown");
  await page.goto("/people/demand");
  await expect(source).toContainText("Win probability: 70.0%");
  await expect(source.getByRole("row").filter({ hasText: "America/New_York" }).getByRole("cell").nth(2)).toHaveText("2");
  await expect(source.getByRole("row").filter({ hasText: "Asia/Kolkata" }).getByRole("cell").nth(2)).toHaveText("5");
  await sourcing(true);
  await page.goto(`/forecast?view=opportunities&account_id=${fixture.client_id}&as_of=2026-10-01T12:00:00Z`);
  await page.getByRole("button", { name: "Edit assumptions", exact: true }).click();
  const editor = page.getByRole("form", { name: "Edit planning assumptions" });
  await editor.getByLabel("Win probability (0 to 1)").fill("0.40");
  await editor.getByLabel("Probability source").fill("Synthetic review lowers likelihood, not team size");
  await editor.getByLabel("Change reason").fill("Probability changes must not weight headcount");
  await editor.getByRole("button", { name: "Save revision" }).click();
  await expect(page.getByRole("region", { name: "Next opportunities", exact: true })).toContainText("Version 2");
  await page.goto(url);
  await expect(source).toContainText("stale");
  await source.getByRole("button", { name: "Publish demand", exact: true }).click();
  await source.getByRole("textbox", { name: "Publication reason", exact: true }).fill("Publish revised probability, preserve staffing and capability");
  await source.getByRole("button", { name: "Publish latest source", exact: true }).click();
  await expect(source).toContainText("Win probability: 40.0%");
  await expect(source.getByRole("row").filter({ hasText: "America/New_York" }).getByRole("cell").nth(2)).toHaveText("2");
  await expect(source.getByRole("row").filter({ hasText: "Asia/Kolkata" }).getByRole("cell").nth(2)).toHaveText("5");
  const worker = execFileSync(resolve(api, ".venv/bin/python"), ["-m", "worker.forecast_plans"], {
    cwd: resolve(api, ".."), encoding: "utf8", timeout: 45_000,
    env: { ...process.env, PYTHONPATH: api, POSTGRES_URL: "postgresql+asyncpg://s21@127.0.0.1:55421/s21_journey",
      DEALGATE_ENV: "local", DEALGATE_TENANT_ID: "s21-lead" },
  });
  expect(JSON.parse(worker.trim().split("\n").at(-1)!).handled).toBeGreaterThanOrEqual(1);
  const persisted = await request.get(`${base}/forecast/plans?account_id=${fixture.client_id}`, { headers });
  expect(persisted.ok()).toBe(true);
  expect((await persisted.json()).items[0].job.status).toBe("done");
  const outlookResponse = await request.get(`${base}/forecast/outlook?account_id=${fixture.client_id}&as_of=2026-10-01T12:00:00Z&future_quarters=4`, { headers });
  expect(outlookResponse.ok()).toBe(true);
  const outlook = await outlookResponse.json();
  // Jan-Apr: 4/6 of two $420,000 fees; 86 weekdays * 8h * 7 people * $60, both at 40%.
  expect(outlook.future.revenue).toMatch(/^224000(?:\.0+)?$/);
  expect(outlook.future.cost).toMatch(/^115584(?:\.0+)?$/);
  expect(outlook.unresolved_sources).toEqual([]);
  await page.reload();
  await expect(source).toContainText("Synthetic HR confirms India");
  await page.getByRole("button", { name: "Upside", exact: true }).click();
  await expect(page.getByRole("button", { name: "Upside", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(source.getByRole("row").filter({ hasText: "America/New_York" }).getByRole("cell").nth(2)).toHaveText("2");
  await expect(source.getByRole("row").filter({ hasText: "Asia/Kolkata" }).getByRole("cell").nth(2)).toHaveText("5");
  await page.getByRole("button", { name: "Expected", exact: true }).click();
  await expect(source).toContainText("Win probability: 40.0%");
  await expect(page.getByText("Loading forecast...", { exact: true })).not.toBeVisible();
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/resource-demand-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/resource-demand-mobile.png", fullPage: true });
  const response = await request.get(`${base}/people/demand/allocation?account_id=${fixture.client_id}`, { headers });
  expect(response.ok()).toBe(true);
  const allocation = await response.json();
  const november = allocation.intervals.find((item: { start: string }) => item.start === "2026-11-01");
  expect(november.demands.reduce((total: number, item: { quantity: number }) => total + item.quantity, 0)).toBe(7);
  expect(november.demands.every((item: { plan_id: string; probability: string }) => item.plan_id === plan.id && /^0\.4(?:0+)?$/.test(item.probability))).toBe(true);
  expect(allocation.is_reservation).toBe(false);
  await page.setViewportSize({ width: 1280, height: 800 });
  await sourcing(false);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/sourcing-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/sourcing-mobile.png", fullPage: true });
  const demandResponse = await request.get(`${base}/people/demand`, { headers });
  const published = (await demandResponse.json()).items.find((item: { plan_id: string }) => item.plan_id === plan.id);
  const historyResponse = await request.get(`${base}/people/sourcing/drafts?publication_id=${published.publication_id}`, { headers });
  expect(historyResponse.ok()).toBe(true);
  const history = await historyResponse.json();
  expect(history.state).toBe("current");
  expect(history.items.map((item: { revision: number }) => item.revision)).toEqual([2, 1]);
  expect(history.items[0].snapshot.probability).toMatch(/^0\.4(?:0+)?$/);
  expect(history.items[1].snapshot.probability).toMatch(/^0\.7(?:0+)?$/);
  expect(errors).toEqual([]);
});
