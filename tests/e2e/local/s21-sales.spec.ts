import { expect, test } from "@playwright/test";

// Reads the real local journey, never supplies feature responses or approval state.
test("S21 Sales and HR decisions persist in the real review stream", async ({ page, baseURL }) => {
  expect(baseURL).toBe("http://127.0.0.1:5210");
  const deal = process.env.S21_JOURNEY_DEAL;
  expect(deal, "Run scripts/s21_real_journey.py and pass its isolated deal ID").toBeTruthy();
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(`/sows/${deal}/approvals`);
  await expect(page.getByRole("heading", { name: "Review stream" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Sales.*Approved$/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^HR.*Approved$/ })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: /^Sales.*Approved$/ })).toBeVisible();
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/sales-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: /^Sales.*Approved$/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/sales-mobile.png", fullPage: true });
  expect(errors).toEqual([]);
});
