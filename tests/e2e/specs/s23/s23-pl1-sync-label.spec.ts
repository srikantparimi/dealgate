/**
 * S23-PL1 item 8, carried by the S23-PL2 page · the Pipeline's freshness line follows the last successful
 * deal sync (run records, served in GET /api/pipeline/workspace → freshness, the same dict as
 * GET /api/hubspot/sync-health), never the intake heartbeat that froze on 2026-10-01 ("13d ago").
 *
 * Read-only: it signs in as the e2e bot, opens /pipeline and reads the line. It creates no data.
 *
 *   STAGING_E2E_USERNAME=e2e-staging@smartek21.com E2E_BASE_URL=https://app.dealgateapp.com \
 *     npx playwright test specs/s23/s23-pl1-sync-label.spec.ts
 */
import { expect, test } from "@playwright/test";

import { authStaging } from "../../fixtures/staging-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";

test("Pipeline freshness line reads the last successful deal sync, not the intake heartbeat", async ({ page }) => {
  await authStaging(page, BASE);
  const answered = page.waitForResponse(
    (r) => r.url().includes("/api/pipeline/workspace") && r.request().method() === "GET" && r.status() === 200,
  );
  await page.goto(`${BASE}/pipeline`);
  const body = (await (await answered).json()) as { freshness: { state: string; last_success_at: string | null } };
  expect(["fresh", "stale", "failed"]).toContain(body.freshness.state);
  expect(body.freshness.last_success_at).toBeTruthy();

  const line = page.getByText(/Deals synced .* PT|Deal data is \d+ days? old|The last sync failed/).first();
  await expect(line).toBeVisible();
  if (body.freshness.state === "fresh") {
    const hours = Math.round((Date.now() - Date.parse(body.freshness.last_success_at!)) / 3_600_000);
    await expect(page.getByText(new RegExp(`· (${hours - 1}|${hours}|${hours + 1}) h ago · nightly sync`))).toBeVisible();
  }
  // The frozen heartbeat read in days; the line never measures it.
  await expect(page.getByText(/1[2-9]d ago|\d{2,}d ago/)).toHaveCount(0);
  await line.screenshot({ path: "screenshots/s23-pl1-sync-line.png" });
});
