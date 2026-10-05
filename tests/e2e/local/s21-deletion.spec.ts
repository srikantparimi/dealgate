import { expect, test } from "@playwright/test";

test("deletion result shows real cleanup status and retained project", async ({ page }) => {
  const jobId = process.env.S21_DELETION_JOB;
  if (!jobId) throw new Error("S21_DELETION_JOB must name the real isolated deletion journey result");
  await page.goto(`/deletions/${jobId}`);
  await expect(page.getByRole("heading", { name: "SOW deletion" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Deletion status");
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).not.toContainText(jobId.slice(0, 8));
  await expect(page.getByText("File cleanup complete", { exact: true })).toBeVisible();
  await expect(page.getByText("retained projects: 1", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Projects" }).last()).toHaveAttribute("href", "/projects");
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/deletion-result-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(page.getByText("File cleanup complete", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/deletion-result-mobile.png", fullPage: true });
});
