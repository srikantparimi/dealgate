import { readFileSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test("T18 coverage clear restores exact nonempty demand and project link retains context", async ({ page, request }) => {
  test.setTimeout(90_000);
  page.setDefaultTimeout(15_000);
  if (!process.env.S21_VIEWS_COVERAGE_MANIFEST) throw new Error("Require owned C receipt");
  const f = JSON.parse(readFileSync(process.env.S21_VIEWS_COVERAGE_MANIFEST, "utf8"));
  expect(f.database).toMatch(/^s21_cov_37eb[0-9a-f]{28}$/);
  const headers = { "X-Test-User": f.actor_email };
  const base = "http://127.0.0.1:8210";
  async function get(path: string) {
    const response = await request.get(`${base}${path}`, { headers });
    expect(response.status()).toBe(200);
    return response.json();
  }
  async function quantities() {
    const result = await get(`/people/demand/allocation?account_id=${f.account_id}`);
    expect(result.is_reservation).toBe(false);
    return result.intervals.map((row: { start: string; end: string; demands: { quantity: number }[] }) => ({
      start: row.start, heads: row.demands.reduce((sum, demand) => sum + demand.quantity, 0),
    }));
  }
  const sources = (await get("/people/demand")).items;
  const plan = sources.find((item: { plan_id: string }) => item.plan_id === f.plan_id);
  const project = sources.find((item: { project_id: string }) => item.project_id === f.project_id);
  const before = (await get(`/people/demand/coverage?plan_publication_id=${plan.publication_id}`)).items[0];
  expect(before.revision).toBe(51);
  expect(before.mappings).toHaveLength(1);
  const covered = await quantities();
  expect(covered).toEqual([
    { start: "2027-01-01", heads: 8 }, { start: "2027-01-15", heads: 7 },
    { start: "2027-02-01", heads: 7 }, { start: "2027-02-16", heads: 8 }, { start: "2027-03-01", heads: 8 },
  ]);
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const query = new URLSearchParams({ view: "resources", account_id: f.account_id, scenario: "expected", as_of: "2026-10-15T12:00:00Z", future_quarters: "2" });
  await page.goto(`/forecast?${query}`);
  const source = page.getByRole("region", { name: f.plan_title, exact: true });
  await source.getByRole("button", { name: "Staffing coverage", exact: true }).click();
  const editor = source.getByRole("region", { name: "Staffing coverage", exact: true });
  await editor.getByLabel("Replacement project", { exact: true }).selectOption(project.publication_id);
  await editor.getByLabel("Coverage reason", { exact: true }).fill("Verify exact nonempty demand after explicit clear");
  await editor.getByRole("button", { name: "Clear coverage", exact: true }).click();
  await expect(editor.getByText("Coverage revision 52 saved", { exact: true })).toBeVisible();
  const cleared = await quantities();
  expect(cleared).toEqual([
    { start: "2027-01-01", heads: 8 }, { start: "2027-02-01", heads: 8 }, { start: "2027-03-01", heads: 8 },
  ]);
  const current = (await get(`/people/demand/coverage?plan_publication_id=${plan.publication_id}`)).items[0];
  expect(current.mappings).toEqual([]);
  const restored = await request.post(`${base}/people/demand/coverage`, { headers, data: {
    plan_publication_id: plan.publication_id, project_publication_id: project.publication_id,
    expected_plan_version_id: plan.publication_version_id, expected_project_version_id: project.publication_version_id,
    expected_mapping_version_id: current.version_id, request_key: crypto.randomUUID(),
    reason: "Restore the exact pre-check mapping without changing prior history", mappings: before.mappings,
  } });
  expect(restored.status()).toBe(201);
  expect((await restored.json()).revision).toBe(53);
  expect(await quantities()).toEqual(covered);
  writeFileSync("../../docs/s21/evidence/baseline/t18-coverage-clear-proof.json", JSON.stringify({
    database: f.database, account_id: f.account_id, before: before.version_id, cleared: current.version_id,
    covered, uncovered: cleared, restored_revision: 53, stage: "restored",
  }, null, 2));
  await page.getByRole("region", { name: f.project_title, exact: true }).getByRole("link", { name: f.project_title, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/people/demand#demand-${f.project_id}$`));
  await expect(page.getByRole("region", { name: f.project_title, exact: true })).toBeInViewport();
  await page.goBack();
  await expect(page.getByText("Loading forecast...", { exact: true })).not.toBeVisible({ timeout: 15_000 });
  for (const [key, value] of query) expect(new URL(page.url()).searchParams.get(key)).toBe(value);
  await expect(page.getByRole("region", { name: f.project_title, exact: true })).toBeVisible();
});
