import { defineConfig, devices } from "@playwright/test";

/**
 * DealGate Playwright config (S7 wave 3).
 *
 * The suite exercises the running Vite dev server + FastAPI dev server
 * against a shared Postgres. Because the DB is shared and every spec
 * seeds real rows via the API, we run one worker so specs never race.
 *
 * The workflow that wraps this (`.github/workflows/e2e.yml`) starts:
 *   - `uvicorn app.main:app` on :8000 with `DEALGATE_ENV=local` and
 *     `DEALGATE_TEST_GROUPS` set to every role (so the per-request
 *     `X-Test-User` header alone decides identity — role gates are
 *     satisfied by the process-wide env var).
 *   - `npm run dev` on :5173 with `VITE_TEST_USER=<owner>@smartek21.com`
 *     as the default identity for the browser (specs override per
 *     request via a Playwright request context header).
 */
const E2E_BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./specs",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: E2E_BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
