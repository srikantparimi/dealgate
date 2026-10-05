import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("T19 final date move removes December and current-quarter contribution", async ({ page, request }) => {
  test.setTimeout(90_000);
  page.setDefaultTimeout(15_000);
  const f = JSON.parse(readFileSync("/tmp/s21-preview-ab7182f1.json", "utf8"));
  expect(f.database).toBe("s21_preview_ab7182f1866844428bd8b5c134bae80f");
  const source = f.sources.find((s: { key: string }) => s.key === "meridian-next");
  const headers = { "X-Test-User": f.actor_email };
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const query = `as_of=${encodeURIComponent(f.as_of)}&scenario=expected&future_quarters=2`;
  const response = await request.get(`http://127.0.0.1:8210/forecast/outlook?${query}`, { headers });
  expect(response.status()).toBe(200);
  const company = await response.json();
  expect(company.current_quarter.revenue).toBe("690200");
  expect(company.months.find((m: { start: string }) => m.start === "2026-12-01").revenue).toBe("228200");
  expect(company.rows.filter((r: { source_id: string; month: string }) => r.source_id === source.plan_id && r.month === "2026-12-01")).toEqual([]);
  const account = company.accounts.find((a: { account_id: string }) => a.account_id === source.account_id);
  expect(account.current_quarter.revenue).toBe("45000");
  expect(account.future.revenue).toBe("18000");
  expect(company.future.cost).toBe("395840");
  const financial: unknown[] = [];
  for (const [scenario, revenue, cost, future] of [
    ["committed", "0", "0", "174000"],
    ["expected", "18000", "9000", "684400"],
    ["upside", "36000", "18000", "930400"],
  ]) {
    const result = await request.get(`http://127.0.0.1:8210/forecast/outlook?as_of=${encodeURIComponent(f.as_of)}&scenario=${scenario}&future_quarters=2`, { headers });
    expect(result.status()).toBe(200);
    const value = await result.json();
    expect(value.future.revenue).toBe(future);
    const sourceRows = value.rows.filter((r: { source_id: string }) => r.source_id === source.plan_id);
    expect(sourceRows).toHaveLength(1);
    expect(sourceRows[0]).toMatchObject({ month: "2027-01-01", revenue, cost,
      source_version: "eeeacfd9-8677-418a-91eb-d58fe5468cb3" });
    financial.push({ scenario, revenue, cost, company_future: future, source_version: sourceRows[0].source_version });
  }
  await page.goto(`/forecast?${query}`);
  await expect(page.getByRole("button", { name: "Export rows", exact: true })).toBeEnabled();
  await expect(page.getByRole("heading", { name: "Current quarter", exact: true }).locator("..")).toContainText("USD 690200");
  await page.getByRole("tab", { name: "Revenue projection", exact: true }).click();
  await page.getByRole("button", { name: "Inspect December 2026", exact: true }).click();
  const rows = page.getByRole("region", { name: "Forecast source rows", exact: true });
  await expect(rows).not.toContainText(source.title);
  await page.goto(`/forecast?${query}&account_id=${source.account_id}`);
  await expect(page.getByRole("button", { name: "Export rows", exact: true })).toBeEnabled();
  await expect(page.getByRole("heading", { name: "Current quarter", exact: true }).locator("..")).toContainText("USD 45000");
  writeFileSync("../../docs/s21/evidence/baseline/t19-preview-old-period.json", JSON.stringify({
    revision: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    application: "44fec5163c722e87eaeb69f0c486ce32a875d4c0", database: f.database,
    company_current_quarter: "690200", december: "228200", account_current_quarter: "45000",
    old_source_rows: 0, final_account_future: "18000", company_future_cost: "395840", financial,
  }, null, 2));
});

test("T19 accepted preview date value and probability edits reconcile after reload", async ({ page, request }) => {
  test.setTimeout(240_000);
  page.setDefaultTimeout(15_000);
  const f = JSON.parse(readFileSync("/tmp/s21-preview-ab7182f1.json", "utf8"));
  expect(f.database).toBe("s21_preview_ab7182f1866844428bd8b5c134bae80f");
  const source = f.sources.find((s: { key: string }) => s.key === "meridian-next");
  const headers = { "X-Test-User": f.actor_email };
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const operations: unknown[] = [];
  function proof(item: unknown) {
    operations.push(item);
    writeFileSync("../../docs/s21/evidence/baseline/t19-preview-edits.json", JSON.stringify({
      revision: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
      database: f.database, operations,
    }, null, 2));
  }
  async function plan() {
    const response = await request.get(`http://127.0.0.1:8210/forecast/plans?account_id=${source.account_id}`, { headers });
    expect(response.status()).toBe(200);
    return (await response.json()).items.find((p: { id: string }) => p.id === source.plan_id);
  }
  async function loaded() {
    await expect(page.getByRole("button", { name: "Export rows", exact: true })).toBeEnabled();
    await expect(page.getByText("Loading forecast...", { exact: true })).not.toBeVisible();
  }
  function worker() {
    const output = execFileSync(resolve("../../api/.venv/bin/python"), ["-m", "worker.forecast_plans"], {
      cwd: resolve("../.."), encoding: "utf8", timeout: 60_000,
      env: { ...process.env, PYTHONPATH: resolve("../../api"), DEALGATE_ENV: "local", DEALGATE_TENANT_ID: f.database,
        POSTGRES_URL: `postgresql+asyncpg://s21@127.0.0.1:55421/${f.database}` },
    });
    expect(JSON.parse(output.trim().split("\n").at(-1)!).handled).toBe(1);
  }
  const url = `/forecast?account_id=${source.account_id}&as_of=${encodeURIComponent(f.as_of)}&future_quarters=2&scenario=expected&view=opportunities`;
  const original = await plan();
  expect(original.version).toBe(1);
  expect(original.commercial_inputs.pricing.total_fee).toBe("30000");
  await page.goto(url); await loaded();
  const article = page.getByRole("article", { name: source.title, exact: true });
  const editor = page.getByRole("region", { name: "Edit planning commercial terms", exact: true });
  async function reconcile(label: string, expected: string, company: string, upside: string, probability: string) {
    await page.reload(); await loaded();
    const current = await plan();
    expect(current.probability).toBe(probability);
    expect(current.commercial_inputs.service_start).toBe("2027-01-01");
    expect(current.commercial_inputs.service_end).toBe("2027-01-31");
    expect(current.commercial_inputs.pricing.allocations[0].month).toBe("2027-01-01");
    expect(current.commercial_inputs.costs[0].month).toBe("2027-01-01");
    for (const [scenario, value] of [["expected", expected], ["upside", upside], ["committed", "0"]]) {
      const response = await request.get(`http://127.0.0.1:8210/forecast/outlook?account_id=${source.account_id}&as_of=${encodeURIComponent(f.as_of)}&scenario=${scenario}`, { headers });
      expect(response.status()).toBe(200);
      const body = await response.json();
      expect(body.future.revenue).toBe(value);
      expect(body.pending_sources).toEqual([]); expect(body.unresolved_sources).toEqual([]);
    }
    const total = await request.get(`http://127.0.0.1:8210/forecast/outlook?as_of=${encodeURIComponent(f.as_of)}`, { headers });
    expect((await total.json()).future.revenue).toBe(company);
    await page.getByRole("tab", { name: "Company & accounts", exact: true }).click(); await loaded();
    await expect(page.getByRole("heading", { name: "Next 2 full quarters", exact: true }).locator("..")).toContainText(`USD ${expected}`);
    await page.getByRole("tab", { name: "Overview", exact: true }).click(); await loaded();
    const row = page.getByRole("region", { name: "Overview sources", exact: true }).getByRole("row").filter({ hasText: source.title });
    await expect(row).toContainText("2027-01-01");
    await expect(row.getByRole("cell").nth(6)).toHaveText(expected);
    await page.getByRole("tab", { name: "Revenue projection", exact: true }).click(); await loaded();
    await page.getByRole("button", { name: "Inspect January 2027", exact: true }).click();
    const revenue = page.getByRole("region", { name: "Forecast source rows", exact: true });
    await expect(revenue).toContainText(source.title); await expect(revenue).toContainText(expected);
    await page.getByRole("tab", { name: "Resource demand", exact: true }).click(); await loaded();
    await expect(page.getByRole("region", { name: "Resource demand", exact: true })).toBeVisible();
    await page.goto(url); await loaded();
    await expect(article).toContainText("Calculation: done");
    await article.getByRole("button", { name: "Edit commercial terms", exact: true }).click();
    await expect(editor.getByLabel("Total fee", { exact: true })).toHaveValue(upside);
    await editor.getByRole("button", { name: "Cancel commercial edit", exact: true }).click();
    proof({ label, version_id: current.version_id, version: current.version, expected, company, upside, probability });
  }
  await article.getByRole("button", { name: "Edit commercial terms", exact: true }).click();
  await editor.getByLabel("Service start", { exact: true }).fill("2027-01-01");
  await editor.getByLabel("Service end", { exact: true }).fill("2027-01-31");
  await editor.getByLabel("Allocation month 1", { exact: true }).fill("2027-01-01");
  await editor.getByLabel("Cost month 1", { exact: true }).fill("2027-01-01");
  await editor.getByLabel("Commercial change reason", { exact: true }).fill("T19 explicit January service and cost allocation, not automatic shifting");
  await editor.getByRole("button", { name: "Save commercial revision", exact: true }).click();
  await expect(editor).not.toBeVisible(); worker();
  await reconcile("date", "10500", "676900", "30000", "0.35");
  await article.getByRole("button", { name: "Edit commercial terms", exact: true }).click();
  await editor.getByLabel("Total fee", { exact: true }).fill("36000");
  await editor.getByLabel("Commercial change reason", { exact: true }).fill("T19 independently revised fixed fee, cost stays18000");
  await editor.getByRole("button", { name: "Save commercial revision", exact: true }).click();
  await expect(editor).not.toBeVisible(); worker();
  await reconcile("value", "12600", "679000", "36000", "0.35");
  await article.getByRole("button", { name: "Edit assumptions", exact: true }).click();
  const assumptions = page.getByRole("form", { name: "Edit planning assumptions", exact: true });
  await assumptions.getByLabel("Win probability (0 to 1)", { exact: true }).fill("0.5");
  await assumptions.getByLabel("Probability source", { exact: true }).fill("Explicit synthetic customer review");
  await assumptions.getByLabel("Change reason", { exact: true }).fill("T19 fifty percent confidence with unchanged full service cost");
  await assumptions.getByRole("button", { name: "Save revision", exact: true }).click();
  await expect(assumptions).not.toBeVisible(); worker();
  await reconcile("probability", "18000", "684400", "36000", "0.5");
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t19-preview-edits-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(article).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t19-preview-edits-mobile.png", fullPage: true });
});
