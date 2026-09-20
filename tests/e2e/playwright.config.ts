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

// Staging runs are slower — the whole flow crosses CloudFront, ALB, ECS
// Fargate, RDS and Bedrock — so timeouts bump when the base URL is the
// deployed one. Local dev keeps the tight numbers.
const IS_STAGING = /d1mu2un4hj9akj\.cloudfront\.net|dealgate\.smartek21\.com/.test(
  E2E_BASE_URL,
);

export default defineConfig({
  testDir: "./specs",
  timeout: IS_STAGING ? 180_000 : 30_000,
  expect: { timeout: IS_STAGING ? 20_000 : 5_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: E2E_BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: IS_STAGING ? 45_000 : 10_000,
    navigationTimeout: IS_STAGING ? 60_000 : 15_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
