import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("T13 partial mixed-location calendars resolve missing inputs and retain exact economics", async ({ page, request }) => {
  const root = resolve(process.cwd(), "../..");
  const api = "http://127.0.0.1:8210";
  const headers = { "X-Test-User": `s21-t13-${randomUUID()}@example.test` };
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const issued = await request.post(`${api}/dev/test-fixtures`, { headers, data: { label: "T13 calendar proof", reviewer_ids: [] } });
  expect(issued.status()).toBe(201);
  const fixture = await issued.json();
  const output = execFileSync(`${root}/api/.venv/bin/python`, ["scripts/s21_conflict_review_journey.py"], {
    cwd: root, encoding: "utf8", timeout: 30_000, env: { ...process.env, PYTHONPATH: `${root}/api:${root}`,
      POSTGRES_URL: "postgresql+asyncpg://s21@127.0.0.1:55421/s21_journey", DEALGATE_ENV: "local",
      DEALGATE_TENANT_ID: "s21-lead", S21_REVIEW_DEAL: fixture.opportunity_id },
  });
  const source = JSON.parse(output.trim().split("\n").at(-1)!);
  const registryResponse = await request.get(`${api}/delivery-model/commercial/profiles`, { headers });
  expect(registryResponse.ok()).toBe(true);
  const policy = (await registryResponse.json()).policy.version;
  const base = { version: "1", source_id: source.sow_id, source_version: source.version_id, profile_version: "1",
    policy_version: policy, source_evidence: ["Independent synthetic T13 date/rate oracle, not extracted"],
    service_start: "2026-10-16", service_end: "2026-10-31", currency: "USD", billing_cadence: "monthly",
    cost_basis: "Synthetic confirmed loaded hourly rates", costs_confirmed: true, costs: [] };
  const child = (location: string, timezone: string, quantity: number, allocation: string, bill: string, cost: string, holiday: string) => ({
    ...base, component_id: location, workstream_id: `${location} calendar`, profile: "calendar_staff_aug", timezone,
    staffing: [{ assignment_id: location, source_id: source.sow_id, source_version: source.version_id, component_id: location,
      profile_version: "1", policy_version: policy, role: `${location} engineer`, location, timezone, currency: "USD",
      quantity, allocation, bill_rate: bill, cost_rate: cost, rate_version: "rates-1", cost_version: "costs-1",
      start: "2026-10-16", end: "2026-10-31", calendar: { calendar_id: `${location}-calendar`, version: "1", timezone,
        coverage_start: "2026-10-16", coverage_end: "2026-10-31",
        week: Array.from({ length: 7 }, (_, i) => ({ scheduled: i < 5 ? "8" : "0", billable: i < 5 ? "8" : "0", paid: i < 5 ? "8" : "0" })),
        overrides: [{ day: holiday, hours: { scheduled: "0", billable: "0", paid: "8" }, reason: `${location} paid holiday` }] } }],
    pricing: { rates: [{ assignment_id: location, basis: "hourly", rate: bill, version: "rates-1", hours_per_day: null, proration: null }] },
  });
  const us = child("US", "America/New_York", 3, "0.25", "120", "33", "2026-10-23");
  const india = child("India", "Asia/Kolkata", 2, "0.5", "80", "40", "2026-10-26");
  const inputs: any = { ...base, component_id: "mixed", workstream_id: "Mixed calendar proof", profile: "hybrid",
    timezone: "UTC", staffing: [], pricing: { components: [us, india], shared_cost_allocations: [],
      allocation_basis: "Direct location costs", minor_unit: "0.01", fx_rates: [] } };
  for (const missing of ["calendar", "cost", "coverage"]) {
    const candidate = structuredClone(inputs);
    const affected = candidate.pricing.components[1].staffing[0];
    if (missing === "calendar") affected.calendar = null;
    if (missing === "cost") affected.cost_rate = null;
    if (missing === "coverage") affected.calendar.coverage_end = "2026-10-27";
    const preview = await request.post(`${api}/delivery-model/commercial/preview`, { headers, data: candidate });
    expect(preview.ok(), await preview.text()).toBe(true);
    const result = await preview.json();
    expect(result.computed.complete).toBe(false);
    expect(result.computed.gm_blended).toBeNull();
    expect(result.computed.policy.india_pass).toBe(false);
    const row = result.commercial_snapshot.schedule.children.find((c: any) => c.component.component_id === "India").calendar_rows[0];
    expect(row.cost).toBeNull();
    if (missing === "cost") expect(Number(row.billable_hours)).toBe(80);
    else expect(row.billable_hours).toBeNull();
  }
  inputs.pricing.components[0].staffing[0].calendar = null;
  inputs.pricing.components[0].staffing[0].cost_rate = null;
  const saved = await request.post(`${api}/delivery-model/${source.deal_id}/commercial/versions`, { headers,
    data: { sow_version_id: source.version_id, expected_gm_model_id: null, inputs, change_reason: "T13 declared missing calendar and loaded rate" } });
  expect(saved.ok(), await saved.text()).toBe(true);
  const initial = (await saved.json()).gm_model;
  expect(initial.computed.complete).toBe(false);
  expect(initial.computed.gm_blended).toBeNull();
  await page.goto(`/sows/${source.deal_id}/staffing`);
  await expect(page.getByText("incomplete", { exact: true }).first()).toBeVisible();
  const persistedResponse = await request.get(`${api}/delivery-model/${source.deal_id}`, { headers });
  expect(persistedResponse.ok()).toBe(true);
  const persisted = (await persistedResponse.json()).gm_model;
  expect(persisted.id).toBe(initial.id);
  const unresolved = persisted.commercial_snapshot.schedule.children.find((c: any) => c.component.component_id === "US").calendar_rows[0];
  expect([unresolved.scheduled_hours, unresolved.billable_hours, unresolved.paid_hours, unresolved.cost]).toEqual([null, null, null, null]);
  const assignment = page.getByRole("region", { name: "Component 1", exact: true }).getByRole("region", { name: "Assignment 1", exact: true });
  await expect(assignment.getByLabel("Loaded cost rate", { exact: true })).toHaveValue("");
  await assignment.getByLabel("Loaded cost rate", { exact: true }).fill("33");
  await assignment.getByRole("button", { name: "Add confirmed calendar" }).click();
  await assignment.getByLabel("Calendar source ID", { exact: true }).fill("US-calendar");
  await assignment.getByLabel("Calendar version", { exact: true }).fill("1");
  for (const [i, day] of ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].entries()) {
    for (const kind of ["scheduled", "billable", "paid"]) await assignment.getByLabel(`${day} ${kind} hours`, { exact: true }).fill(i < 5 ? "8" : "0");
  }
  await assignment.getByRole("button", { name: "Add calendar exception" }).click();
  await assignment.getByLabel("Exception date 1", { exact: true }).fill("2026-10-23");
  await assignment.getByLabel("Exception reason 1", { exact: true }).fill("US paid holiday");
  for (const kind of ["scheduled", "billable", "paid"]) await assignment.getByLabel(`Exception ${kind} hours 1`, { exact: true }).fill(kind === "paid" ? "8" : "0");
  await page.getByLabel("Change reason", { exact: true }).fill("Confirm independent US calendar and loaded cost; no aggregate hours entered");
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  await expect(page.getByText("Commercial version saved.", { exact: true })).toBeVisible();
  await page.reload();
  const response = await request.get(`${api}/delivery-model/${source.deal_id}`, { headers });
  expect(response.ok()).toBe(true);
  const latest = (await response.json()).gm_model;
  expect(latest.id).not.toBe(initial.id);
  expect(latest.computed.complete).toBe(true);
  expect(Number(latest.computed.revenue_us)).toBe(7200);
  expect(Number(latest.computed.revenue_india)).toBe(6400);
  expect(Number(latest.computed.cost_us)).toBe(2178);
  expect(Number(latest.computed.cost_india)).toBe(3520);
  const rows = latest.commercial_snapshot.schedule.calendar_rows;
  expect(rows.map((r: any) => [r.assignment.location, Number(r.scheduled_hours), Number(r.billable_hours), Number(r.paid_hours)]).sort((a: any, b: any) => a[0].localeCompare(b[0]))).toEqual([["India", 80, 80, 88], ["US", 60, 60, 66]]);
  expect(Number(latest.computed.gm_us)).toBe(0.6975);
  expect(Number(latest.computed.gm_india)).toBe(0.45);
  expect(latest.computed.policy.india_pass).toBe(false);
  for (const [location, date, paid] of [["US", "2026-10-23", 6], ["India", "2026-10-26", 8]]) {
    const row = rows.find((r: any) => r.assignment.location === location);
    const day = row.days.find((d: any) => d.day === date);
    expect([Number(day.scheduled_hours), Number(day.billable_hours), Number(day.paid_hours), day.reason]).toEqual([0, 0, paid, `${location} paid holiday`]);
  }
  await expect(page.getByRole("region", { name: "Calendar calculation details", exact: true }).first()).toBeVisible();
  const calendarDetails = page.getByRole("region", { name: "Calendar calculation details", exact: true }).first();
  for (const [location, scheduled, paid] of [["US", 60, 66], ["India", 80, 88]]) {
    const block = calendarDetails.locator(":scope > div").filter({ hasText: `${location} engineer / ${location} / 2026-10-01` });
    const cells = block.getByRole("table").first().locator("tbody").getByRole("cell");
    await expect(cells).toHaveText([new RegExp(`^${scheduled}(?:\\.0+)?$`), new RegExp(`^${scheduled}(?:\\.0+)?$`), new RegExp(`^${paid}(?:\\.0+)?$`)]);
  }
  for (const region of await page.getByRole("region", { name: "Calendar calculation details", exact: true }).all()) {
    for (const summary of await region.getByText("Daily hours and exceptions", { exact: true }).all()) await summary.click();
  }
  await expect(page.getByRole("region", { name: "Calendar calculation details", exact: true }).first()).toBeVisible();
  await expect(page.getByText("US paid holiday", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("India paid holiday", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t13-calendar.png", fullPage: true });
  const detail = page.getByRole("region", { name: "Calendar calculation details", exact: true }).first();
  await detail.screenshot({ path: "../../docs/s21/evidence/baseline/t13-details.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await detail.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t13-mobile.png" });
});
