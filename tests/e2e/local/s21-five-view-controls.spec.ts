import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("T18 planning and publication controls persist changes and period-filter full staffing", async ({ page, request }) => {
  test.setTimeout(180_000);
  page.setDefaultTimeout(15_000);
  if (!process.env.S21_VIEWS_MANIFEST) throw new Error("Require guarded five-view fixture");
  const f = JSON.parse(readFileSync(process.env.S21_VIEWS_MANIFEST, "utf8"));
  expect(f.database).toMatch(/^s21_cov_37eb[0-9a-f]{28}$/);
  const headers = { "X-Test-User": f.actor_email };
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const api = resolve(process.cwd(), "../../api");
  const log: unknown[] = [];
  function checkpoint(value: unknown) {
    log.push(value);
    writeFileSync("../../docs/s21/evidence/baseline/t18-controls-proof.json", JSON.stringify({
      run_id: f.run_id, database: f.database, operations: log,
    }, null, 2));
  }
  function worker() {
    const output = execFileSync(resolve(api, ".venv/bin/python"), ["-m", "worker.forecast_plans"], {
      cwd: resolve(api, ".."), encoding: "utf8", timeout: 60_000,
      env: { ...process.env, PYTHONPATH: api, POSTGRES_URL: `postgresql+asyncpg://s21@127.0.0.1:55421/${f.database}`,
        DEALGATE_ENV: "local", DEALGATE_TENANT_ID: f.database },
    });
    const result = JSON.parse(output.trim().split("\n").at(-1)!);
    expect(result.handled).toBeGreaterThanOrEqual(1);
    checkpoint({ worker: result });
  }
  async function plan() {
    const response = await request.get(`http://127.0.0.1:8210/forecast/plans?account_id=${f.account_a_id}`, { headers });
    expect(response.status()).toBe(200);
    return (await response.json()).items.find((item: { id: string }) => item.id === f.plan_a_id);
  }
  const before = await plan();
  expect(before.probability).toMatch(/^0\.5(?:0+)?$/);
  await page.goto(`/forecast?view=overview&month=2027-01-01&as_of=${encodeURIComponent(f.as_of)}&future_quarters=2`);
  const overview = page.getByRole("region", { name: "Overview sources", exact: true });
  const january = overview.getByRole("row").filter({ hasText: f.plan_a_title });
  await expect(january).toContainText("2027-01-01");
  await expect(january.getByRole("cell").nth(6)).toHaveText("100");
  await january.getByRole("button", { name: f.account_a_name, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`account_id=${f.account_a_id}`));
  await january.getByRole("button", { name: f.plan_a_title, exact: true }).click();
  await expect(page.getByRole("region", { name: "Source detail", exact: true })).toContainText(before.version_id);
  await page.getByRole("button", { name: "Close source detail", exact: true }).click();
  await expect(page.getByRole("button", { name: "Previous source page", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Next source page", exact: true })).toBeDisabled();
  await page.getByRole("tab", { name: "Company & accounts", exact: true }).click();
  await page.getByLabel("As of (UTC)", { exact: true }).fill("2027-01-15");
  const currentQuarter = page.getByRole("heading", { name: "Current quarter", exact: true }).locator("..");
  await expect(currentQuarter).toContainText("2027-01-01 to 2027-04-01");
  await expect(currentQuarter).toContainText("USD 300");
  await expect(page.getByRole("heading", { name: "Next 2 full quarters", exact: true }).locator("..")).toContainText("USD 0");
  const url = `/forecast?account_id=${f.account_a_id}&as_of=${encodeURIComponent(f.as_of)}&future_quarters=2&view=opportunities`;
  await page.goto(url);
  const article = page.getByRole("article", { name: f.plan_a_title, exact: true });
  await article.getByRole("button", { name: "Edit assumptions", exact: true }).click();
  const editor = page.getByRole("form", { name: "Edit planning assumptions", exact: true });
  await expect(editor.getByRole("button", { name: "Save revision", exact: true })).toBeDisabled();
  await editor.getByRole("combobox", { name: "Planning status", exact: true }).selectOption("dismissed");
  await editor.getByLabel("Win probability (0 to 1)", { exact: true }).fill("0.9");
  await editor.getByRole("button", { name: "Cancel", exact: true }).click();
  expect((await plan()).version_id).toBe(before.version_id);
  await article.getByRole("button", { name: "Edit assumptions", exact: true }).click();
  await editor.getByLabel("Win probability (0 to 1)", { exact: true }).fill("1.2");
  await editor.getByLabel("Change reason", { exact: true }).fill("Rejected synthetic probability");
  await editor.getByRole("button", { name: "Save revision", exact: true }).click();
  await expect(editor.getByRole("alert")).toBeVisible();
  expect((await plan()).version_id).toBe(before.version_id);
  await editor.getByLabel("Win probability (0 to 1)", { exact: true }).fill("0.6");
  await editor.getByLabel("Probability source", { exact: true }).fill("Synthetic sales review, documented sixty percent");
  await editor.getByLabel("Assumptions", { exact: true }).fill("Same full service staffing; revised probability only");
  await editor.getByRole("combobox", { name: "Planning status", exact: true }).selectOption("won_unsigned");
  await editor.getByLabel("Change reason", { exact: true }).fill("T18 connected assumption controls");
  await editor.getByRole("button", { name: "Save revision", exact: true }).click();
  await expect(editor).not.toBeVisible();
  const revised = await plan();
  expect(revised.version).toBe(before.version + 1);
  expect(revised.assumptions).toEqual(["Same full service staffing; revised probability only"]);
  expect(revised.lifecycle).toBe("won_unsigned");
  expect(revised.probability_source).toBe("Synthetic sales review, documented sixty percent");
  checkpoint({ action: "assumptions", before: before.version_id, after: revised.version_id });
  worker();
  await page.reload();
  await expect(article).toContainText("Win probability: 60.0%");
  await expect(article).toContainText("Calculation: done");
  await expect(article).toContainText("won unsigned");
  await expect(article).toContainText("Synthetic sales review, documented sixty percent");
  const response = await request.get(`http://127.0.0.1:8210/forecast/outlook?account_id=${f.account_a_id}&as_of=${encodeURIComponent(f.as_of)}`, { headers });
  expect(response.status()).toBe(200);
  expect((await response.json()).future.revenue).toBe("360");

  await page.getByRole("tab", { name: "Resource demand", exact: true }).click();
  const source = page.getByRole("region", { name: f.plan_a_title, exact: true });
  await source.getByRole("button", { name: "Publish demand", exact: true }).click();
  await source.getByLabel("Publication reason", { exact: true }).fill("Confirm the complete dated staffing source");
  await source.getByRole("button", { name: "Publish latest source", exact: true }).click();
  await expect(source).toContainText("2027-01-01 to 2027-03-31");
  await expect(source.getByRole("row").nth(1).getByRole("cell").nth(2)).toHaveText("1");
  await source.getByRole("button", { name: "Revise demand", exact: true }).click();
  await source.getByLabel("Skills for Engineer", { exact: true }).fill("discarded-skill");
  await source.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(source).not.toContainText("discarded-skill");
  await source.getByRole("button", { name: "Revise demand", exact: true }).click();
  await source.getByLabel("Skills for Engineer", { exact: true }).fill("python");
  await source.getByLabel("Level for Engineer", { exact: true }).fill("Senior");
  await source.getByLabel("Evidence for Engineer", { exact: true }).fill("Synthetic staffing capability confirmation");
  await source.getByLabel("Publication reason", { exact: true }).fill("Document skills and level without changing headcount");
  await source.getByRole("button", { name: "Publish latest source", exact: true }).click();
  await expect(source).toContainText("python");
  await page.getByRole("button", { name: "Reload sources", exact: true }).click();
  await expect(source).toContainText("Synthetic staffing capability confirmation");
  await expect(source).toContainText("Senior");
  const publishedResponse = await request.get("http://127.0.0.1:8210/people/demand", { headers });
  expect(publishedResponse.status()).toBe(200);
  const published = (await publishedResponse.json()).items.find((item: { plan_id: string }) => item.plan_id === f.plan_a_id);
  expect(published.state).toBe("current");
  expect(published.source_version_id).toBe(revised.version_id);
  expect(published.publication_version_id).toBeTruthy();
  expect(published.lines[0]).toMatchObject({ skills: ["python"], level: "Senior", quantity: 1 });
  checkpoint({ action: "capability", publication_version_id: published.publication_version_id });
  await page.route("**/api/people/demand", route => route.abort("failed"));
  await page.getByRole("button", { name: "Reload sources", exact: true }).click();
  await expect(page.getByRole("region", { name: "Resource demand", exact: true }).getByRole("alert")).toBeVisible();
  await expect(source.getByRole("button", { name: "Revise demand", exact: true })).toBeDisabled();
  await page.unroute("**/api/people/demand");
  await page.getByRole("button", { name: "Reload sources", exact: true }).click();
  await expect(source.getByRole("button", { name: "Revise demand", exact: true })).toBeEnabled();
  await source.getByRole("button", { name: "Staffing coverage", exact: true }).click();
  const coverage = source.getByRole("region", { name: "Staffing coverage", exact: true });
  await coverage.getByRole("button", { name: "Reload latest coverage", exact: true }).click();
  await expect(coverage.getByLabel("Replacement project", { exact: true })).toBeEnabled();
  await source.getByRole("button", { name: "Staffing coverage", exact: true }).click();
  await expect(coverage).not.toBeVisible();

  await page.getByRole("button", { name: "All accounts", exact: true }).click();
  const second = page.getByRole("region", { name: f.plan_b_title, exact: true });
  await second.getByRole("button", { name: "Publish demand", exact: true }).click();
  await second.getByLabel("Publication reason", { exact: true }).fill("Confirm second-quarter staffing for horizon comparison");
  await second.getByRole("button", { name: "Publish latest source", exact: true }).click();
  await expect(second).toContainText("2027-04-01 to 2027-06-30");
  await page.getByLabel("Future quarters", { exact: true }).selectOption("1");
  await expect(source).toBeVisible();
  await expect(second).not.toBeVisible();
  await page.getByLabel("Future quarters", { exact: true }).selectOption("2");
  await expect(second).toBeVisible();
  await page.getByRole("tab", { name: "Revenue projection", exact: true }).click();
  await page.getByRole("button", { name: "April 2027", exact: true }).click();
  await page.getByRole("tab", { name: "Resource demand", exact: true }).click();
  await expect(second).toBeVisible();
  await expect(source).not.toBeVisible();
  await expect(second.getByRole("row").nth(1).getByRole("cell").nth(2)).toHaveText("1");
  await page.getByRole("button", { name: "Upside", exact: true }).click();
  await expect(second.getByRole("row").nth(1).getByRole("cell").nth(2)).toHaveText("1");
  checkpoint({ action: "publication-and-period", plans: [f.plan_a_id, f.plan_b_id], probability_weighted_heads: false });

  // Restore the fixture's original probability by a new immutable UI revision.
  await page.goto(url);
  await article.getByRole("button", { name: "Edit assumptions", exact: true }).click();
  await editor.getByLabel("Win probability (0 to 1)", { exact: true }).fill("0.5");
  await editor.getByLabel("Probability source", { exact: true }).fill(before.probability_source);
  await editor.getByLabel("Assumptions", { exact: true }).fill(before.assumptions.join("\n"));
  await editor.getByRole("combobox", { name: "Planning status", exact: true }).selectOption(before.lifecycle);
  await editor.getByLabel("Change reason", { exact: true }).fill("Restore declared fixture assumption through a new revision");
  await editor.getByRole("button", { name: "Save revision", exact: true }).click();
  await expect(editor).not.toBeVisible();
  worker();
  const restored = await plan();
  expect(restored.version).toBe(before.version + 2);
  expect(restored.probability).toMatch(/^0\.5(?:0+)?$/);
  expect(restored.probability_source).toBe(before.probability_source);
  expect(restored.assumptions).toEqual(before.assumptions);
  expect(restored.lifecycle).toBe(before.lifecycle);
  expect(restored.job.status).toBe("done");
  const finalOutlook = await request.get(`http://127.0.0.1:8210/forecast/outlook?account_id=${f.account_a_id}&as_of=${encodeURIComponent(f.as_of)}`, { headers });
  expect(finalOutlook.status()).toBe(200);
  expect((await finalOutlook.json()).future.revenue).toBe("300");
  checkpoint({ action: "restored-by-revision", version_id: restored.version_id, status: "passed" });
});
