import { expect, test, type Page } from "@playwright/test";

const api = "http://127.0.0.1:8210";
const headers = { "X-Test-User": "s21-browser@example.test" };
const fixtures = JSON.parse(process.env.S21_EDITOR_FIXTURES || "{}");

function component(profile: string, fixture: { sow: string; version: string }, policy: string): any {
  const base = {
    component_id: `component-${profile}`, version: "1", source_id: fixture.sow, source_version: fixture.version,
    workstream_id: `Synthetic ${profile}`, profile, profile_version: "1", policy_version: policy,
    source_evidence: ["Synthetic independently specified editor fixture; not extracted"],
    service_start: "2026-10-01", service_end: "2026-10-02", timezone: "America/New_York", currency: "USD",
    billing_cadence: "monthly", cost_basis: "Confirmed synthetic loaded cost", costs_confirmed: true,
    costs: [{ source_id: `cost-${profile}`, month: "2026-10-01", location: "US", amount: "1000" }], staffing: [],
  };
  const pricing: Record<string, unknown> = {
    fixed_assignment: { total_fee: "24000", allocations: [{ month: "2026-10-01", location: "US", weight: "1" }], allocation_basis: "Single service month", minor_unit: "0.01" },
    recurring_msp: { fees: [{ location: "US", amount: "20000" }], proration: "full_month", included_scope: "Two tickets",
      adjustments: [{ source_id: "credit", month: "2026-10-01", location: "US", kind: "credit", amount: "41" }],
      usage: [{ source_id: "tickets", month: "2026-10-01", location: "US", unit: "ticket", quantity: "13", included_quantity: "2", unit_rate: "9" }] },
    unit: { rate: "125", unit: "ticket", quantities: [{ source_id: "unit-quantity", month: "2026-10-01", location: "US", quantity: "10" }], contractual_basis: "billable_units" },
  };
  return { ...base, pricing: profile === "hybrid" ? {
    components: [component("fixed_assignment", fixture, policy), component("unit", fixture, policy)],
    shared_cost_allocations: [], allocation_basis: "Direct attribution", minor_unit: "0.01", fx_rates: [],
  } : pricing[profile] ?? null, ...(profile === "hybrid" ? { costs: [] } : {}) };
}

async function addCalendar(page: Page) {
  await page.getByRole("button", { name: "Add assignment", exact: true }).click();
  await expect(page.getByLabel("Loaded cost rate", { exact: true })).toHaveValue("");
  await page.getByLabel("Role", { exact: true }).fill("Engineer");
  await page.getByLabel("Assignment location", { exact: true }).selectOption("US");
  await page.getByLabel("Headcount", { exact: true }).fill("2");
  await page.getByLabel("Allocation fraction", { exact: true }).fill("0.5");
  await page.getByLabel("Loaded cost rate", { exact: true }).fill("40");
  await page.getByLabel("Cost source version", { exact: true }).fill("synthetic-rates-v1");
  await page.getByRole("button", { name: "Add confirmed calendar" }).click();
  await page.getByLabel("Calendar source ID", { exact: true }).fill("synthetic-calendar");
  await page.getByLabel("Calendar version", { exact: true }).fill("1");
  for (const [index, day] of ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].entries()) {
    for (const kind of ["scheduled", "billable", "paid"]) {
      await page.getByLabel(`${day} ${kind} hours`, { exact: true }).fill(index < 5 ? "8" : "0");
    }
  }
}

for (const profile of ["fixed_assignment", "recurring_msp", "hybrid", "custom_formula"]) {
  test(`${profile}: real editor defect regression with immutable saved economics`, async ({ page, request }) => {
    const fixture = fixtures[profile];
    expect(fixture, "Owned runner fixture is required").toBeTruthy();
    const registry = await request.get(`${api}/delivery-model/commercial/profiles`, { headers });
    expect(registry.ok()).toBe(true);
    const inputs = component(profile, fixture, (await registry.json()).policy.version);
    const saved = await request.post(`${api}/delivery-model/${fixture.deal}/commercial/versions`, { headers,
      data: { sow_version_id: fixture.version, expected_gm_model_id: null, inputs, change_reason: "Synthetic editor regression initial source" } });
    expect(saved.ok(), await saved.text()).toBe(true);
    const first = (await saved.json()).gm_model;
    await page.goto(`/sows/${fixture.deal}/staffing`);
    await expect(page.getByRole("heading", { name: "Commercial model", exact: true })).toBeVisible();
    if (profile === "custom_formula") {
      await expect(page.getByRole("alert").filter({ hasText: "Unsupported commercial model" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Save version", exact: true })).toBeDisabled();
      await expect(page.getByRole("button", { name: "Preview", exact: true })).toBeDisabled();
      await page.getByLabel("Replacement pricing profile", { exact: true }).selectOption("fixed_assignment");
      await page.getByRole("button", { name: "Replace unsupported pricing terms", exact: true }).click();
      await expect(page.getByLabel("Pricing profile", { exact: true })).toHaveValue("fixed_assignment");
      await expect(page.getByRole("alert").filter({ hasText: "Unsupported commercial model" })).toHaveCount(0);
      const original = await request.get(`${api}/delivery-model/${fixture.deal}`, { headers });
      expect((await original.json()).gm_model.id).toBe(first.id);
      await page.getByLabel("Total fee", { exact: true }).fill("24000");
      await page.getByLabel("Allocation basis", { exact: true }).fill("Confirmed single service month");
      await page.getByLabel("Currency minor unit", { exact: true }).fill("0.01");
      await page.getByRole("button", { name: "Add allocation", exact: true }).click();
      await page.getByLabel("Allocation month 1", { exact: true }).fill("2026-10-01");
      await page.getByLabel("Allocation location 1", { exact: true }).selectOption("US");
      await page.getByLabel("Allocation weight 1", { exact: true }).fill("1");
      await page.getByLabel("Change reason", { exact: true }).fill("Explicit correction of unsupported synthetic legacy model");
      await page.getByRole("button", { name: "Save version", exact: true }).click();
      await expect(page.getByText("Commercial version saved.", { exact: true })).toBeVisible();
      await page.reload();
      await expect(page.getByLabel("Pricing profile", { exact: true })).toHaveValue("fixed_assignment");
      const correction = await request.get(`${api}/delivery-model/${fixture.deal}`, { headers });
      const corrected = (await correction.json()).gm_model;
      expect(corrected.id).not.toBe(first.id);
      expect(corrected.commercial_inputs.source_evidence).toEqual(inputs.source_evidence);
      expect(Number(corrected.computed.revenue_us)).toBe(24000);
      expect(Number(corrected.computed.cost_us)).toBe(1000);
      return;
    }
    if (profile === "hybrid") {
      await page.getByRole("region", { name: "Component 1", exact: true }).getByLabel("Component pricing profile").selectOption("milestone");
      await page.getByRole("button", { name: "Remove component 1" }).click();
      await expect(page.getByRole("button", { name: "Replace component pricing" })).toHaveCount(0);
    } else {
      await addCalendar(page);
      if (profile === "recurring_msp") {
        await page.getByLabel("Adjustment amount 1", { exact: true }).fill("17");
        await page.getByLabel("Overage unit rate 1", { exact: true }).fill("10");
      }
    }
    await page.getByRole("button", { name: "Preview", exact: true }).click();
    await expect(page.getByText("Unsaved preview", { exact: true })).toBeVisible();
    await page.getByLabel("Workstream", { exact: true }).fill(`Confirmed ${profile}`);
    await expect(page.getByText("Unsaved preview; edits not calculated", { exact: true })).toBeVisible();
    await expect(page.getByText("Saved calculation; edits not calculated", { exact: true })).toHaveCount(0);
    await page.getByLabel("Change reason", { exact: true }).fill("Independent editor defect proof with confirmed synthetic calendar");
    await page.getByRole("button", { name: "Save version", exact: true }).click();
    await expect(page.getByText("Commercial version saved.", { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("Workstream", { exact: true })).toHaveValue(`Confirmed ${profile}`);
    const response = await request.get(`${api}/delivery-model/${fixture.deal}`, { headers });
    expect(response.ok()).toBe(true);
    const latest = (await response.json()).gm_model;
    expect(latest.id).not.toBe(first.id);
    // Two weekdays * eight paid hours * two people * half allocation * $40, plus $1000 direct cost.
    expect(Number(latest.computed.cost_us)).toBe(profile === "hybrid" ? 1000 : 1640);
    // MSP: $20000 - $17 credit + (13-2) units * $10. Unit sibling: ten * $125.
    expect(Number(latest.computed.revenue_us)).toBe(profile === "hybrid" ? 1250 : profile === "recurring_msp" ? 20093 : 24000);
    if (profile === "hybrid") expect(latest.commercial_inputs.pricing.components[0].profile).toBe("unit");
    else expect(latest.commercial_inputs.staffing[0].quantity).toBe(2);
    await page.screenshot({ path: `../../docs/s21/evidence/baseline/editor-${profile}-desktop.png`, fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `../../docs/s21/evidence/baseline/editor-${profile}-mobile.png`, fullPage: true });
  });
}
