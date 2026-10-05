import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

const tabs = [
  ["company", "Company & accounts"], ["overview", "Overview"],
  ["revenue", "Revenue projection"], ["opportunities", "Next opportunities"],
  ["resources", "Resource demand"],
] as const;

test("T18 persisted five-view navigation retains scope, period and scenario with exact totals", async ({ page, request }) => {
  test.setTimeout(180_000);
  if (!process.env.S21_VIEWS_MANIFEST) throw new Error("Require guarded five-view fixture manifest");
  const f = JSON.parse(readFileSync(process.env.S21_VIEWS_MANIFEST, "utf8"));
  expect(f.database).toMatch(/^s21_cov_37eb[0-9a-f]{28}$/);
  expect(f.status).toBe("ready_for_browser");
  const headers = { "X-Test-User": f.actor_email };
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const query = new URLSearchParams({ as_of: f.as_of, future_quarters: "2", scenario: "expected" });
  async function loaded() {
    await expect(page.getByRole("button", { name: "Export rows", exact: true })).toBeEnabled();
    await expect(page.getByText("Loading forecast...", { exact: true })).not.toBeVisible();
  }
  async function outlook(extra: Record<string, string> = {}) {
    const response = await request.get(`http://127.0.0.1:8210/forecast/outlook?${new URLSearchParams({ ...Object.fromEntries(query), ...extra })}`, { headers });
    expect(response.status()).toBe(200);
    return response.json();
  }
  const original = await outlook();
  // Independent fee oracle: A600/3 months *50%; B240/3 months *25%.
  expect(original.current_month.revenue).toBe("24000");
  expect(original.current_quarter.revenue).toBe("24000");
  expect(original.future.revenue).toBe("360");
  expect((await outlook({ future_quarters: "1" })).future.revenue).toBe("300");
  expect((await outlook({ scenario: "upside" })).future.revenue).toBe("840");
  expect((await outlook({ scenario: "committed" })).future.revenue).toBe("0");
  await page.goto(`/forecast?${query}`);
  await loaded();
  const accounts = page.getByRole("region", { name: "Account outlook", exact: true });
  await expect(accounts.getByRole("button", { name: f.account_a_name, exact: true })).toBeVisible();
  await expect(accounts.getByRole("button", { name: f.account_b_name, exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Current quarter", exact: true }).locator("..")).toContainText("USD 24000");
  await expect(page.getByRole("heading", { name: "Next 2 full quarters", exact: true }).locator("..")).toContainText("USD 360");
  for (const [scenario, total] of [["Committed", "0"], ["Upside", "840"], ["Expected", "360"]]) {
    await page.getByRole("button", { name: scenario, exact: true }).click();
    await loaded();
    await expect(page.getByRole("heading", { name: "Next 2 full quarters", exact: true }).locator("..")).toContainText(`USD ${total}`);
  }
  await accounts.getByRole("button", { name: f.account_a_name, exact: true }).click();
  await loaded();
  await expect(page.locator("main > header")).toContainText(f.account_a_name);
  await expect(page.getByRole("heading", { name: "Next 2 full quarters", exact: true }).locator("..")).toContainText("USD 300");
  await page.getByRole("button", { name: "Upside", exact: true }).click();
  await loaded();
  await page.getByRole("combobox", { name: "Future quarters", exact: true }).selectOption("4");
  await loaded();
  await page.getByRole("button", { name: "Inspect January 2027", exact: true }).click();
  await expect(page.getByRole("region", { name: "Forecast source rows", exact: true }).getByRole("row")).toHaveCount(2);
  const selected = { account_id: f.account_a_id, scenario: "upside", future_quarters: "4", as_of: f.as_of, month: "2027-01-01" };
  for (const [view, title] of tabs) {
    await page.getByRole("tab", { name: title, exact: true }).click();
    await loaded();
    await expect(page.getByRole("tab", { name: title, exact: true })).toHaveAttribute("aria-selected", "true");
    const params = new URL(page.url()).searchParams;
    for (const [key, value] of Object.entries(selected)) expect(params.get(key)).toBe(value);
    expect(params.get("view")).toBe(view);
    await expect(page.locator("main > header")).toContainText(f.account_a_name);
  }
  const demand = page.getByRole("region", { name: f.plan_a_title, exact: true });
  await expect(demand).toBeVisible();
  await demand.getByRole("link", { name: f.plan_a_title, exact: true }).click();
  await loaded();
  for (const [key, value] of Object.entries(selected)) expect(new URL(page.url()).searchParams.get(key)).toBe(value);
  await expect(page.getByRole("tab", { name: "Next opportunities", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.goBack();
  await loaded();
  await expect(page.getByRole("tab", { name: "Resource demand", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Revenue projection", exact: true }).click();
  const rows = page.getByRole("region", { name: "Forecast source rows", exact: true });
  await rows.getByRole("button", { name: f.plan_a_title, exact: true }).click();
  const detail = page.getByRole("region", { name: "Source detail", exact: true });
  await expect(detail).toContainText("commercial-schedule-v1");
  await detail.getByRole("link", { name: f.plan_a_title, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/deals/${f.deal_a_id}`));
  await expect(page.getByRole("heading").first()).toBeVisible();
  await page.goBack();
  await loaded();
  for (const [key, value] of Object.entries(selected)) expect(new URL(page.url()).searchParams.get(key)).toBe(value);
  await rows.getByRole("button", { name: f.plan_a_title, exact: true }).click();
  await detail.getByRole("button", { name: "Close source detail", exact: true }).click();
  await expect(detail).not.toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export rows", exact: true }).click();
  const path = await (await download).path();
  const csv = JSON.parse(execFileSync(resolve(process.cwd(), "../../api/.venv/bin/python"), ["-c",
    "import csv,json,sys; print(json.dumps(list(csv.DictReader(sys.stdin))))"], { input: readFileSync(path!, "utf8"), encoding: "utf8" }));
  expect(csv).toHaveLength(1);
  expect(csv[0]).toMatchObject({ account_id: f.account_a_id, account_name: f.account_a_name,
    source_id: f.plan_a_id, source_name: f.plan_a_title, month: "2027-01-01", scenario: "upside", revenue: "200" });
  await page.getByRole("button", { name: "Clear month filter", exact: true }).click();
  await page.getByRole("button", { name: "December 2027", exact: true }).click();
  await page.getByRole("combobox", { name: "Future quarters", exact: true }).selectOption("1");
  await loaded();
  await expect(page.getByRole("button", { name: "Clear month filter", exact: true })).not.toBeVisible();
  await page.getByRole("button", { name: "All accounts", exact: true }).click();
  await loaded();
  await page.getByRole("tab", { name: "Resource demand", exact: true }).click();
  await expect(page.getByRole("region", { name: f.plan_a_title, exact: true })).toBeVisible();
  const demandResponse = await request.get("http://127.0.0.1:8210/people/demand", { headers });
  expect(demandResponse.status()).toBe(200);
  const b = (await demandResponse.json()).items.find((item: { plan_id: string }) => item.plan_id === f.plan_b_id);
  expect(["current", "pending", "stale"]).toContain(b.state);
  // Before publication unresolved B stays visible; after publication its April dates exclude it.
  if (b.state === "current") await expect(page.getByRole("region", { name: f.plan_b_title, exact: true })).not.toBeVisible();
  else await expect(page.getByRole("region", { name: f.plan_b_title, exact: true })).toBeVisible();
  await page.getByLabel("As of (UTC)", { exact: true }).fill("2026-10-16");
  await loaded();
  expect(new URL(page.url()).searchParams.get("as_of")).toBe("2026-10-16T00:00:00Z");
  await page.getByLabel("As of (UTC)", { exact: true }).fill("");
  await loaded();
  expect(new URL(page.url()).searchParams.has("as_of")).toBe(false);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t18-views-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t18-views-mobile.png", fullPage: true });
  expect(errors).toEqual([]);
  writeFileSync("../../docs/s21/evidence/baseline/t18-views-proof.json", JSON.stringify({
    revision: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    database: f.database, run_id: f.run_id, scenario: "T18", boundary: "Local identity and seeded signed prerequisite; not staging",
    original, exported_rows: csv, verified: ["five persisted views", "scope/period/scenario and Back", "independent quarterly totals", "selected-month CSV", "horizon invalidation"],
  }, null, 2));
});

test("T18 all five views retain an empty account name and recover from a real transport interruption", async ({ page }) => {
  test.setTimeout(120_000);
  if (!process.env.S21_VIEWS_MANIFEST) throw new Error("Require guarded five-view fixture manifest");
  const f = JSON.parse(readFileSync(process.env.S21_VIEWS_MANIFEST, "utf8"));
  expect(f.database).toMatch(/^s21_cov_37eb[0-9a-f]{28}$/);
  await page.route("**/api/**", route => route.continue({ headers: {
    ...route.request().headers(), "X-Test-User": f.actor_email,
  } }));
  for (const [view, title] of tabs) {
    const query = new URLSearchParams({ view, account_id: f.empty_account_id,
      as_of: f.as_of, future_quarters: "2", scenario: "expected" });
    await page.goto(`/forecast?${query}`);
    await expect(page.getByRole("button", { name: "Export rows", exact: true })).toBeEnabled();
    await expect(page.locator("main > header")).toContainText(f.empty_account_name);
    await expect(page.locator("main > header")).not.toContainText(f.empty_account_id);
    await expect(page.getByRole("tab", { name: title, exact: true })).toHaveAttribute("aria-selected", "true");
    if (view === "company") {
      await expect(page.getByRole("region", { name: "Account outlook", exact: true })).toContainText(f.empty_account_name);
      await expect(page.getByRole("heading", { name: "Next 2 full quarters", exact: true }).locator("..")).toContainText("USD 0");
    } else {
      const empty = view === "resources" ? "No demand sources" : view === "opportunities"
        ? "No planning opportunities in this scope." : "No eligible source rows for this period.";
      await expect(page.getByText(empty, { exact: true })).toBeVisible();
    }
    // Fault injection aborts transport; no fabricated feature response or automatic retry.
    await page.route("**/api/forecast/outlook?**", route => route.abort("failed"));
    await page.getByRole("button", { name: "Refresh forecast", exact: true }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("button", { name: "Export rows", exact: true })).toBeDisabled();
    await page.unroute("**/api/forecast/outlook?**");
    await page.getByRole("button", { name: "Refresh forecast", exact: true }).click();
    await expect(page.getByRole("button", { name: "Export rows", exact: true })).toBeEnabled();
    await expect(page.getByRole("alert")).not.toBeVisible();
    await expect(page.locator("main > header")).toContainText(f.empty_account_name);
    expect(new URL(page.url()).searchParams.get("view")).toBe(view);
  }
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t18-empty-recovery.png", fullPage: true });
});
