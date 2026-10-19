import { defineConfig } from "@playwright/test";

/**
 * S24-AG1 · T9 + T14 Playwright config for specs/s24 (lane T-D).
 *
 * LOCAL (the default): a stack on loopback only — three APIs on one seeded Postgres database
 * (scripts/s24_ag1_local_seed.py; SystemAdmin on 8241, Legal on 8242, Sales on 8243, because
 * DEALGATE_TEST_GROUPS is process-wide) and one Vite on 5241 that proxies /api to 8241
 * (DEALGATE_DEV_API_URL + VITE_API_BASE_URL=/api: the API sends no CORS headers). The spec sends the
 * Legal and Sales pages' API calls to their own API with page routes.
 *
 * STAGING (E2E_MODE=staging, run by the lead after the deploy): the same spec signs in as the e2e bot and
 * works only on run-tagged fixtures; timeouts grow as in playwright.config.ts.
 *
 * Browser: the installed Google Chrome (channel "chrome"), because this machine has no Playwright-managed
 * Chromium and the lane may not download one. Set E2E_BROWSER_CHANNEL="" to use the bundled Chromium.
 */
const STAGING = process.env.E2E_MODE === "staging";
if (!process.env.E2E_MODE) process.env.E2E_MODE = "local";
const channel = process.env.E2E_BROWSER_CHANNEL ?? "chrome";

export default defineConfig({
  testDir: "./specs/s24",
  outputDir: process.env.E2E_OUTPUT_DIR ?? "test-results/s24",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: STAGING ? 300_000 : 120_000,
  expect: { timeout: STAGING ? 20_000 : 10_000 },
  reporter: [["list"]],
  use: {
    baseURL: STAGING ? (process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com") : (process.env.S24_LOCAL_WEB ?? "http://127.0.0.1:5241"),
    channel: channel || undefined,
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: STAGING ? 45_000 : 15_000,
    navigationTimeout: STAGING ? 60_000 : 30_000,
  },
});
