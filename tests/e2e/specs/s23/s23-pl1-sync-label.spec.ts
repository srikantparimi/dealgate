/**
 * S23-PL1 item 8 · on the old Pipeline page, "Last synced" follows the last
 * successful deal sync (GET /api/hubspot/sync-health → last_success_at), not
 * the intake heartbeat that has been frozen since 2026-10-01 ("13d ago").
 *
 * Read-only: it signs in as the e2e bot, opens /pipeline and reads the banner.
 * It creates no data, so the run-tag gate has nothing to clean.
 *
 *   STAGING_E2E_USERNAME=e2e-staging@smartek21.com E2E_BASE_URL=https://app.dealgateapp.com \
 *     npx playwright test specs/s23/s23-pl1-sync-label.spec.ts
 */
import { expect, test } from "@playwright/test";

import { authStaging } from "../../fixtures/staging-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";

test("Pipeline 'Last synced' reads sync-health, not the intake heartbeat", async ({ page }) => {
  await authStaging(page, BASE);
  const health = page.waitForResponse(
    (r) => r.url().endsWith("/api/hubspot/sync-health") && r.request().method() === "GET",
  );
  await page.goto(`${BASE}/pipeline`);
  const response = await health;
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(["fresh", "stale", "failed"]).toContain(body.state);
  expect(body.last_success_at).toBeTruthy();

  const banner = page.getByTestId("sync-banner");
  await expect(banner).toContainText("Last synced");
  // The heartbeat reads in days; the last successful sync is minutes or hours old.
  await expect(banner).toContainText(/Last synced\s*(just now|\d+ min ago|\d+h ago)/);
  await expect(banner).not.toContainText(/\d+d ago/);
  await banner.screenshot({ path: "screenshots/s23-pl1-sync-banner.png" });
});
