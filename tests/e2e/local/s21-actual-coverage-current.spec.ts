import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test("T21 current estimate remains exact after concurrent replay and responsive reload", async ({ page, request }) => {
  if (!process.env.S21_COV_MANIFEST) throw new Error("Require existing repaired T21 fixture");
  const f = JSON.parse(readFileSync(process.env.S21_COV_MANIFEST, "utf8"));
  expect(f.database).toMatch(/^s21_cov_[0-9a-f]{32}$/);
  const headers = { "X-Test-User": f.actor_email };
  const key = crypto.randomUUID();
  const data = { source_system: `replay-${key}`, idempotency_key: key, rows: [{
    account_id: f.account_id, gm_model_id: f.gm_model_id, source_id: "uncovered-replay",
    period_month: f.month, measure: "recognized_revenue", amount: "1", currency: "USD",
    source_date: f.cutoff, revision: 1, expected_previous_revision: 0,
    reason: "Synthetic concurrent request identity proof, coverage unconfirmed",
  }] };
  const results = await Promise.all([1, 2].map(() => request.post("http://127.0.0.1:8210/actuals/financial-import", { headers, data })));
  expect(results.map(row => row.status())).toEqual([201, 201]);
  const batches = await Promise.all(results.map(row => row.json()));
  expect(batches[0].id).toBe(batches[1].id);
  const sql = `SELECT json_build_object('facts',(SELECT count(*) FROM financial_actual WHERE source_system='replay-${key}'),'batches',(SELECT count(*) FROM financial_import_batch WHERE source_system='replay-${key}'))`;
  expect(JSON.parse(execFileSync("docker", ["exec", "dealgate-s21-lead-db", "psql", "-U", "s21", "-d", f.database, "-At", "-c", sql], { encoding: "utf8" })))
    .toEqual({ facts: 1, batches: 1 });
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  await page.goto(`/forecast?view=overview&account_id=${f.account_id}`);
  const estimate = page.getByRole("region", { name: "Current-period signed estimate", exact: true });
  const revenue = estimate.getByRole("row").filter({ hasText: "Recognized revenue" });
  await expect(revenue.getByRole("cell").nth(7)).toHaveText("22500");
  await expect(estimate.getByRole("row").filter({ hasText: "Delivery cost" }).getByRole("cell").nth(7)).toHaveText("11000");
  await expect(revenue.getByTitle(f.sow_version_id)).toHaveText(`Version ${f.sow_version_id.slice(0, 8)}`);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t21-current-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(revenue.getByRole("cell").nth(7)).toHaveText("22500");
  const overflow = estimate.locator("div.overflow-x-auto");
  expect(await overflow.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true);
  const bounds = await estimate.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t21-current-mobile.png", fullPage: true });
});
