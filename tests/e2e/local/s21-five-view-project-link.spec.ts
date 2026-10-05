import { readFileSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test("T18 project demand link reaches its exact source and Back retains Forecast context", async ({ page }) => {
  test.setTimeout(45_000);
  page.setDefaultTimeout(15_000);
  if (!process.env.S21_VIEWS_COVERAGE_MANIFEST) throw new Error("Require owned C receipt");
  const f = JSON.parse(readFileSync(process.env.S21_VIEWS_COVERAGE_MANIFEST, "utf8"));
  expect(f.database).toMatch(/^s21_cov_37eb[0-9a-f]{28}$/);
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), "X-Test-User": f.actor_email } }));
  const query = new URLSearchParams({ view: "resources", account_id: f.account_id, scenario: "expected", as_of: "2026-10-15T12:00:00Z", future_quarters: "2" });
  await page.goto(`/forecast?${query}`);
  const source = page.getByRole("region", { name: f.project_title, exact: true });
  await source.getByRole("link", { name: f.project_title, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/people/demand#demand-${f.project_id}$`));
  await expect(page.getByRole("heading", { name: "People planning", exact: true })).toBeVisible();
  await expect(source).toBeInViewport();
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t18-project-demand-link.png" });
  await page.goBack();
  await expect(page.getByText("Loading forecast...", { exact: true })).not.toBeVisible({ timeout: 15_000 });
  for (const [key, value] of query) expect(new URL(page.url()).searchParams.get(key)).toBe(value);
  await expect(source).toBeVisible();
  writeFileSync("../../docs/s21/evidence/baseline/t18-project-link-proof.json", JSON.stringify({
    account_id: f.account_id, project_id: f.project_id, source: `/people/demand#demand-${f.project_id}`,
    returned_context: Object.fromEntries(query), result: "passed",
  }, null, 2));
});
