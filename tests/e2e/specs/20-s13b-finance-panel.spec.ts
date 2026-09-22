import { test, expect } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";

const opportunity = "13130000-0000-0000-0000-000000000001";
const screenshots = path.resolve(__dirname, "../../../docs/reports/s13b");

test("S13b costs change engine GM, pass-through stays outside, and Confirm round-trips", async ({ page }) => {
  test.skip(!process.env.S13B_LOCAL_PROOF, "Requires the isolated s13b_local.py fixture server");
  test.setTimeout(90_000);
  fs.mkdirSync(screenshots, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(`/sows/${opportunity}/staffing`);
  const summary = page.getByRole("region", { name: "GM summary" });
  await expect(summary.getByText("42.4%", { exact: true }).first()).toBeVisible();
  await expect(summary.getByText("Passes US floor", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Add cost", exact: true }).click();
  await page.getByLabel("Cost category 1", { exact: true }).selectOption("Software/licenses");
  await page.getByLabel("Cost description 1", { exact: true }).fill("Delivery software");
  await page.getByLabel("Cost value 1", { exact: true }).fill("1000");
  await expect(summary.getByText("$29,800", { exact: true })).toBeVisible();
  await expect(summary.getByText("40.4%", { exact: true }).first()).toBeVisible();
  await expect(summary.getByText("2.0% of price", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Add cost", exact: true }).click();
  await page.getByLabel("Cost description 2", { exact: true }).fill("Client-reimbursed travel");
  await page.getByLabel("Cost value 2", { exact: true }).fill("2300");
  await page.getByLabel("Cost reimbursable 2", { exact: true }).check();
  await expect(summary.getByText("$2,300", { exact: true })).toBeVisible();
  await expect(summary.getByText("40.4%", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: path.join(screenshots, "01-staffing-direct-costs.png"), fullPage: true });
  await page.getByTestId("save-staffing").click();
  await page.waitForURL(/opportunityId=/);
  await page.reload();
  const table = page.getByRole("table", { name: "Staffing grid" });
  await expect(table.getByText("$120.00", { exact: true })).toHaveCount(2);
  await expect(table.getByText("— fixed price", { exact: true })).toHaveCount(2);
  await expect(table.getByText("80", { exact: true })).toBeVisible();
  await expect(table.getByText("160", { exact: true })).toBeVisible();
  await expect(table.getByText("100%", { exact: true })).toHaveCount(2);
  await expect(summary.getByText("Not applicable — no India resources")).toBeVisible();
  await expect(summary.getByText("40.4%", { exact: true }).first()).toBeVisible();
  await expect(page.getByLabel("Cost value 1", { exact: true })).toHaveValue(/1000|2300/);
  expect(await page.locator("body").innerText()).not.toMatch(/0\.\d{6,}/);
  await page.screenshot({ path: path.join(screenshots, "02-confirm-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(screenshots, "03-confirm-mobile.png"), fullPage: true });

  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/sows/new?opportunityId=13130000-0000-0000-0000-000000000002");
  await expect(summary.getByRole("meter")).toHaveCount(2);
  await expect(summary.getByText("Fails · India", { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(screenshots, "04-mixed-floors.png"), fullPage: true });
});
