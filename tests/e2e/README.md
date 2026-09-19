# tests/e2e/

Playwright end-to-end scenarios for the ten journeys in blueprint § 11.
This is intentionally separate from `web/`'s vitest suite so unit tests
stay fast — Playwright only runs in CI (see `.github/workflows/e2e.yml`)
or when a developer opts in locally.

## Layout

- `playwright.config.ts` — single-worker (DB is shared), 30 s per test,
  HTML reporter, base URL from `E2E_BASE_URL` (defaults to
  `http://localhost:5173`).
- `fixtures/api.ts` — `apiFetch(role, method, path, body?)` helper that
  injects the `X-Test-User` dev header.
- `fixtures/seed.ts` — helpers to create clients / agreements / SOWs /
  gm_models / approval packages via the API.
- `fixtures/time.ts` — nudges the FastAPI clock via `DEALGATE_NOW` for
  the renewal-alert time-travel scenario (spec skips gracefully if the
  optional `/admin/test/now` endpoint is not exposed).
- `specs/01-…` through `specs/10-…` — one file per blueprint § 11
  scenario. Each starts with `test.describe.configure({ mode: "serial" })`
  because the DB and API are shared.

## Run locally

Assumes:
- FastAPI dev server is running on `:8000` with
  `DEALGATE_ENV=local` and `DEALGATE_TEST_GROUPS` containing every role
  (`SystemAdmin,Sales,Delivery,Finance,Legal,HR,CEO,Presales,Marketing,SalesLeader`).
  This grants role gates process-wide so per-request `X-Test-User`
  headers can freely change identity.
- Vite dev server is running on `:5173` with
  `VITE_TEST_USER=sales@smartek21.com` (the specs override per request
  via a Playwright request-level route hook).
- Real integrations are stubbed:
  `S3_STUB=1 SOW_EXTRACT_STUB=1 SIGNED_SOW_EXTRACT_STUB=1 BEDROCK_STUB=1 SES_STUB=1 HUBSPOT_STUB=1`.

Then:

```
cd tests/e2e
npm install
npx playwright install chromium
npm test
```

Open the HTML report from `playwright-report/index.html` after a run.

## CI

The `e2e` workflow is opt-in:

- **Manual**: Actions → `e2e` → *Run workflow*.
- **Push to `main`**: include `[e2e]` in the commit message.
- **Nightly**: cron `0 4 * * *`.

The workflow boots Postgres, migrates the DB, starts uvicorn + Vite,
installs Playwright, and runs `npm test` from `tests/e2e`. Failure logs
(`uvicorn.log`, `vite.log`) and the HTML report upload as artifacts.

## Adding a scenario

1. Copy an existing spec — keep the `describe.configure({ mode: "serial" })`
   line so specs don't race on the shared DB.
2. Seed the exact preconditions via `fixtures/seed.ts` (extend the file
   if you need a new helper; keep every helper API-only).
3. Assert on visible outcomes with `getByRole` / `getByLabel` /
   `getByText` — never brittle CSS.
4. Only skip a scenario when a stub / dev-only endpoint is missing;
   include a `test.skip(true, "…")` message that names the missing bit.
