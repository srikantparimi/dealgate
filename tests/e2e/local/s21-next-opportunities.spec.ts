import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("planning assumptions persist through UI, worker, and forecast recalculation", async ({ page, request }) => {
  test.setTimeout(90_000);
  const account = process.env.S21_FORECAST_ACCOUNT;
  expect(account, "An isolated Company X planning account is required").toBeTruthy();
  const headers = { "X-Test-User": "s21-browser@example.test" };
  const params = new URLSearchParams({ account_id: account!, as_of: "2026-10-01T12:00:00Z", view: "opportunities" });
  const beforeResponse = await request.get(`http://127.0.0.1:8210/forecast/plans?account_id=${account}`, { headers });
  expect(beforeResponse.ok()).toBe(true);
  const before = (await beforeResponse.json()).items;
  expect(before).toHaveLength(1);
  const original = before[0];
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(`/forecast?${params}`);
  await page.getByRole("tab", { name: "Next opportunities", exact: true }).click();
  const view = page.getByRole("region", { name: "Next opportunities", exact: true });
  await expect(view).toContainText("Synthetic Company X findings, scenario A");
  await expect(view.getByRole("link", { name: "Open linked deal" })).toHaveAttribute("href", `/deals/${original.opportunity_id}`);
  await view.getByRole("button", { name: "Edit assumptions" }).click();
  const editor = page.getByRole("form", { name: "Edit planning assumptions" });
  await editor.getByLabel("Win probability (0 to 1)").fill("0.60");
  await editor.getByLabel("Probability source").fill("Synthetic review with explicit sixty percent likelihood");
  await editor.getByLabel("Assumptions", { exact: true }).fill("Six service months; 7 people, not probability-weighted headcount");
  await editor.getByLabel("Change reason").fill("Connected browser proof of immutable planning assumptions");
  await editor.getByRole("button", { name: "Save revision" }).click();
  await expect(view).toContainText(`Version ${original.version + 1}`);
  await page.reload();
  await expect(page.getByRole("tab", { name: "Next opportunities", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(view).toContainText("sixty percent likelihood");
  await expect(view).toContainText("7 people, not probability-weighted headcount");
  const api = resolve(process.cwd(), "../../api");
  const worker = execFileSync(resolve(api, ".venv/bin/python"), ["-m", "worker.forecast_plans"], {
    cwd: resolve(api, ".."), encoding: "utf8", timeout: 45_000,
    env: { ...process.env, PYTHONPATH: api, POSTGRES_URL: "postgresql+asyncpg://s21@127.0.0.1:55421/s21_journey", DEALGATE_ENV: "local", DEALGATE_TENANT_ID: "s21-lead" },
  });
  expect(JSON.parse(worker.trim().split("\n").at(-1)!).handled).toBeGreaterThanOrEqual(1);
  await page.reload();
  await expect(view).toContainText("Calculation: done");
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/next-opportunities-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/next-opportunities-mobile.png", fullPage: true });
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  await expect(page.getByRole("region", { name: "Forecast overview", exact: true })).toContainText("USD 168000");
  const afterResponse = await request.get(`http://127.0.0.1:8210/forecast/outlook?${params}`, { headers });
  expect(afterResponse.ok()).toBe(true);
  const after = await afterResponse.json();
  expect(after.future.revenue).toMatch(/^168000(?:\.0+)?$/);
  expect(after.future.cost).toMatch(/^84000(?:\.0+)?$/);
  expect(after.financial_actuals.totals.find((r: { measure: string }) => r.measure === "recognized_revenue").amount).toBe("11000.99");
  expect(errors).toEqual([]);
});
