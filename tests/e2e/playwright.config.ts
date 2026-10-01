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
//
// S21-1d: `app.dealgateapp.com` added to the detector — the older
// CloudFront + smartek21.com entries predate the custom-domain
// cutover. Without this, staging runs got local timeouts AND
// included the dev-harness-only specs.
const IS_STAGING = /d1mu2un4hj9akj\.cloudfront\.net|dealgate\.smartek21\.com|app\.dealgateapp\.com/.test(
  E2E_BASE_URL,
);

// S21-1d · item 2: numeric-prefix specs (`01-*.spec.ts` through
// `25-*.spec.ts` outside `specs/s20/`) are dev-harness-only — they
// seed via `fixtures/seed.ts` (`X-Test-User` header + direct SQL
// write) which the Cognito-gated staging API refuses. Running them
// against staging produced 22 expected-but-unlinked reds in the
// pre-S21-1d run; this filter makes the exclusion a config truth,
// not a hidden failure. Reason recorded in
// `docs/reports/s20/tests.md` §"S21-1d · dev-harness-only staging skip".
const DEV_HARNESS_ONLY_ON_STAGING = [
  /\/specs\/0[1-9]-[^/]+\.spec\.ts$/,
  /\/specs\/1[0-9]-[^/]+\.spec\.ts$/,
  /\/specs\/2[0-5]-[^/]+\.spec\.ts$/,
];

export default defineConfig({
  testDir: "./specs",
  testIgnore: IS_STAGING ? DEV_HARNESS_ONLY_ON_STAGING : undefined,
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
