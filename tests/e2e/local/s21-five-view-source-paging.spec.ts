import { readFileSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test("T18 source pagination retains context and does not change forecast economics", async ({ page, request }) => {
  test.setTimeout(90_000);
  page.setDefaultTimeout(15_000);
  if (!process.env.S21_VIEWS_PAGING_MANIFEST) throw new Error("Require guarded paging receipt");
  const f = JSON.parse(readFileSync(process.env.S21_VIEWS_PAGING_MANIFEST, "utf8"));
  expect(f.status).toBe("ready_for_pagination_browser");
  expect(f.database).toMatch(/^s21_cov_37eb[0-9a-f]{28}$/);
  const headers = { "X-Test-User": f.actor_email };
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const query = new URLSearchParams({ account_id: f.account_id, as_of: "2026-10-15T12:00:00Z", future_quarters: "2", scenario: "expected", month: "2027-01-01", view: "opportunities" });
  const outlook = await request.get(`http://127.0.0.1:8210/forecast/outlook?${query}`, { headers });
  expect(outlook.status()).toBe(200);
  const economics = await outlook.json();
  // Signed600 plus a fifty-percent600 plan; dismissed fixtures contribute zero.
  expect(economics.future.revenue).toBe("900");
  const populations = [];
  for (const number of [1, 2]) {
    const response = await request.get(`http://127.0.0.1:8210/forecast/plans?account_id=${f.account_id}&page=${number}&size=50`, { headers });
    expect(response.status()).toBe(200);
    const result = await response.json();
    expect(result.total).toBe(51);
    expect(result.items).toHaveLength(number === 1 ? 50 : 1);
    populations.push(result.items);
  }
  expect(new Set(populations.flat().map(item => item.id)).size).toBe(51);
  await page.goto(`/forecast?${query}`);
  const sources = page.getByRole("region", { name: "Planning sources", exact: true });
  const rows = sources.getByRole("region", { name: "Versioned plans", exact: true }).getByRole("row");
  async function verify(number: number) {
    await expect(page.getByText("Loading forecast...", { exact: true })).not.toBeVisible({ timeout: 15_000 });
    await expect(sources).toContainText(`Page ${number}`);
    await expect(rows).toHaveCount(populations[number - 1].length + 1);
    const names = await rows.locator("td:first-child").allTextContents();
    expect(names).toEqual(populations[number - 1].map(item => item.title));
    const state = new URL(page.url()).searchParams;
    for (const [key, value] of query) expect(state.get(key)).toBe(value);
    expect(state.get("page") ?? "1").toBe(String(number));
  }
  await verify(1);
  const next = sources.getByRole("button", { name: "Next source page", exact: true });
  const previous = sources.getByRole("button", { name: "Previous source page", exact: true });
  await expect(previous).toBeDisabled();
  await expect(next).toBeEnabled();
  await next.click();
  await verify(2);
  await expect(next).toBeDisabled();
  await expect(previous).toBeEnabled();
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  await expect(page).toHaveURL(/view=overview/);
  const last = populations[1][0];
  await page.getByRole("region", { name: "Overview decisions", exact: true }).getByRole("link", { name: last.title, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/deals/${last.opportunity_id}$`));
  await expect(page.getByRole("heading").first()).toBeVisible();
  await page.goBack();
  await page.getByRole("tab", { name: "Next opportunities", exact: true }).click();
  await verify(2);
  await page.getByRole("article", { name: last.title, exact: true }).getByRole("link", { name: "Open linked deal", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/deals/${last.opportunity_id}$`));
  await expect(page.getByRole("heading").first()).toBeVisible();
  await page.goBack();
  await verify(2);
  await previous.click();
  await verify(1);
  await expect(previous).toBeDisabled();
  await expect(next).toBeEnabled();
  if (!process.env.S21_VIEWS_MANIFEST) throw new Error("Require original actuals account receipt");
  const original = JSON.parse(readFileSync(process.env.S21_VIEWS_MANIFEST, "utf8"));
  const actualsQuery = new URLSearchParams({ account_id: original.account_a_id, as_of: original.as_of });
  const actualsResponse = await request.get(`http://127.0.0.1:8210/forecast/outlook?${actualsQuery}`, { headers });
  expect(actualsResponse.status()).toBe(200);
  const exclusions = (await actualsResponse.json()).current_period_estimate.excluded;
  expect(exclusions.length).toBeGreaterThan(0);
  await page.goto(`/forecast?view=company&${actualsQuery}`);
  const estimate = page.getByRole("region", { name: "Current-period signed estimate", exact: true });
  const disclosure = estimate.locator("details");
  await expect(disclosure).not.toHaveAttribute("open", "");
  await disclosure.locator("summary").click();
  await expect(disclosure).toHaveAttribute("open", "");
  for (const row of exclusions) await expect(disclosure.getByText(`${row.id}: ${row.reason}`, { exact: true })).toBeVisible();
  await disclosure.locator("summary").click();
  await expect(disclosure).not.toHaveAttribute("open", "");
  writeFileSync("../../docs/s21/evidence/baseline/t18-source-paging-proof.json", JSON.stringify({
    run_id: f.run_id, account_id: f.account_id, database: f.database,
    future_revenue: economics.future.revenue, pages: populations.map(items => items.map(item => item.id)),
    context: Object.fromEntries(query), exclusions, linked_deal: last.opportunity_id, result: "passed",
  }, null, 2));
});
