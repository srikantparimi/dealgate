import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("explicit staffing replacement reduces demand and preserves clear/history", async ({ page, request }) => {
  test.setTimeout(120_000);
  const headers = { "X-Test-User": "s21-browser@example.test" };
  const base = "http://127.0.0.1:8210";
  const issued = await request.post(`${base}/dev/test-fixtures`, { headers,
    data: { label: "Coverage browser", reviewer_ids: [], hours: 4 } });
  expect(issued.status()).toBe(201);
  const fixture = await issued.json();
  const root = resolve(process.cwd(), "../..");
  const env = { ...process.env, PYTHONPATH: resolve(root, "api"),
    POSTGRES_URL: "postgresql+asyncpg://s21@127.0.0.1:55421/s21_journey",
    DEALGATE_ENV: "local", DEALGATE_TENANT_ID: "s21-lead",
    DEALGATE_REPORTING_TIMEZONE: "America/Los_Angeles", DEALGATE_REPORTING_CURRENCY: "USD" };
  function seed(script: string, extra: Record<string, string>) {
    const output = execFileSync(resolve(root, "api/.venv/bin/python"), [script], {
      cwd: root, encoding: "utf8", timeout: 30_000, env: { ...env, ...extra },
    });
    return JSON.parse(output.trim().split("\n").at(-1)!);
  }
  const project = seed("scripts/s21_retained_journey.py", { S21_RETAINED_DEAL: fixture.opportunity_id });
  const pair = seed("scripts/s21_coverage_journey.py", { S21_COVERAGE_PROJECT: project.project_id });
  expect(pair.fixture_kind).toBe("seeded_release_not_signature_proof");
  async function quantity() {
    const response = await request.get(`${base}/people/demand/allocation?account_id=${pair.account_id}`, { headers });
    expect(response.status()).toBe(200);
    const allocation = await response.json();
    return Math.max(...allocation.intervals.map((i: { demands: { quantity: number }[] }) =>
      i.demands.reduce((sum, row) => sum + row.quantity, 0)));
  }
  expect(await quantity()).toBe(4);
  await page.goto("/people/demand");
  const source = page.getByRole("region", { name: pair.plan_title, exact: true });
  await source.getByRole("button", { name: "Staffing coverage", exact: true }).click();
  const editor = source.getByRole("region", { name: "Staffing coverage", exact: true });
  await editor.getByLabel("Replacement project", { exact: true }).selectOption(pair.project_publication_id);
  await editor.getByRole("button", { name: "Add mapping", exact: true }).click();
  await expect(editor.getByLabel("Plan first slot 1", { exact: true })).toHaveValue("1");
  await expect(editor.getByLabel("Project first slot 1", { exact: true })).toHaveValue("1");
  await expect(editor.getByLabel("Start date 1", { exact: true })).toHaveValue("2026-11-01");
  await expect(editor.getByLabel("End date 1", { exact: true })).toHaveValue("2027-04-30");
  await expect(editor.getByLabel("Slot count 1", { exact: true })).toHaveValue("");
  await editor.getByLabel("Slot count 1", { exact: true }).fill("2");
  await editor.getByLabel("Coverage reason", { exact: true }).fill("Explicit approved replacement for both planned people");
  await editor.getByRole("button", { name: "Save coverage", exact: true }).click();
  await expect(editor.getByText("Coverage revision 1 saved", { exact: true })).toBeVisible();
  expect(await quantity()).toBe(2);
  await page.setViewportSize({ width: 1280, height: 1200 });
  await editor.evaluate((element) => element.scrollIntoView({ block: "center" }));
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/coverage-desktop.png" });
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.reload();
  await source.getByRole("button", { name: "Staffing coverage", exact: true }).click();
  await editor.getByLabel("Replacement project", { exact: true }).selectOption(pair.project_publication_id);
  await expect(editor).toContainText("Coverage revision 1: current");
  await editor.getByLabel("Coverage reason", { exact: true }).fill("Clear coverage after delivery review");
  await editor.getByRole("button", { name: "Clear coverage", exact: true }).click();
  await expect(editor.getByText("Coverage revision 2 saved", { exact: true })).toBeVisible();
  expect(await quantity()).toBe(4);
  const history = await request.get(`${base}/people/demand/coverage?plan_publication_id=${pair.plan_publication_id}`, { headers });
  expect(history.status()).toBe(200);
  const current = (await history.json()).items[0];
  const revisions = await request.get(`${base}/people/demand/coverage?plan_publication_id=${pair.plan_publication_id}&root_id=${current.id}`, { headers });
  expect(revisions.status()).toBe(200);
  const rows = (await revisions.json()).items;
  expect(rows.map((row: { revision: number }) => row.revision)).toEqual([2, 1]);
  expect(rows[0].mappings).toEqual([]);
  expect(rows[1].mappings[0].plan_slots).toEqual([0, 1]);
  await page.setViewportSize({ width: 390, height: 844 });
  await editor.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/coverage-mobile.png" });
  await editor.getByRole("button", { name: "Add mapping", exact: true }).click();
  await editor.getByLabel("Slot count 1", { exact: true }).fill("2");
  await editor.getByLabel("Coverage reason", { exact: true }).fill("Remap before source archive fault");
  await editor.getByRole("button", { name: "Save coverage", exact: true }).click();
  await expect(editor.getByText("Coverage revision 3 saved", { exact: true })).toBeVisible();
  expect(await quantity()).toBe(2);
  expect(seed("scripts/s21_coverage_journey.py", {
    S21_COVERAGE_PROJECT: project.project_id, S21_ARCHIVE_PROJECT: "1",
  }).fixture_kind).toBe("archive_fault_injection");
  await page.reload();
  await source.getByRole("button", { name: "Staffing coverage", exact: true }).click();
  await expect(editor.getByRole("option", { name: /Unavailable mapped project/ })).toHaveCount(1);
  await expect(editor.getByRole("button", { name: "Save coverage", exact: true })).toHaveCount(0);
  await expect(editor).toContainText("Coverage revision 3: stale");
  await editor.getByLabel("Coverage reason", { exact: true }).fill("Clear archived project's obsolete mapping");
  await editor.getByRole("button", { name: "Clear coverage", exact: true }).click();
  await expect(editor.getByText("Coverage revision 4 saved", { exact: true })).toBeVisible();
  expect(await quantity()).toBe(2);
  const allocation = await request.get(`${base}/people/demand/allocation?account_id=${pair.account_id}`, { headers });
  expect(allocation.status()).toBe(200);
  expect((await allocation.json()).missing).not.toContain("staffing_coverage_stale");
});
