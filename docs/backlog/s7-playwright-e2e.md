# S7 — Playwright end-to-end suite covering blueprint §11 scenarios

## User story
As QA / lead, the tests/e2e/ folder currently has only per-story pytest
acceptance tests. Ship a browser-driven Playwright suite that walks the
full journeys called out in blueprint §11: intake → coverage → SOW →
delivery → approvals → CEO exception → signed → release → renewal.

## Acceptance
- `tests/e2e/` initialized with Playwright (@playwright/test).
- Scenarios (one file per scenario):
  - `01-intake-owner-flow.spec.ts` — HubSpot webhook drops a deal (via API call using SystemAdmin) → deal appears in Deal list → owner sees intake task → owner sets engagement type + next check-in date.
  - `02-coverage-nda-msa.spec.ts` — Legal creates NDA + MSA on the client → coverage state transitions from "NDA + MSA missing" → "Complete".
  - `03-sow-upload-confirm.spec.ts` — owner uploads a SOW → confirm-fields screen renders → confirm each field → submit → status moves to SOWDraft.confirmed.
  - `04-delivery-model-gm-below-floor.spec.ts` — Delivery builds a model with US GM = 27.78% → submit for approval → package blocked from Ready-to-Sign, routed to CEO exception.
  - `05-approvals-happy-path.spec.ts` — package where all floors pass → delivery + hr → finance + legal → Ready to Sign; audit trail visible.
  - `06-approvals-nda-missing.spec.ts` — submit_package returns 409 when NDA missing; message shown in UI.
  - `07-ceo-exception.spec.ts` — CEO opens brief, owner writes rationale, CEO approves with conditions + valid_until → package Ready to Sign.
  - `08-signed-sow-diff-blocks.spec.ts` — upload a signed pdf whose price doesn't match the approved package → verify UI shows the diff → release button stays disabled.
  - `09-signed-sow-release.spec.ts` — verified signed pdf → release → renewal record created + kickoff/billing tasks visible.
  - `10-renewal-alert.spec.ts` — time-travel via `DEALGATE_NOW` header → SOW T-60d → renewal appears on the board → nudge notification queued.
- Test runner scripts in `tests/e2e/package.json`: `npm run test` (headless).
- Uses local dev API + web (starts uvicorn + vite from a fixture) OR runs against a `TEST_BASE_URL` env for staging.
- Auth path: `X-Test-User` header pattern (local dev) — no real Cognito in E2E.
- CI job in `.github/workflows/ci.yml` gated on `E2E=true` (opt-in; not on every PR because it's slow).

## Notes
- Playwright is heavier than the pytest AC tests but exercises the real
  React app + API together.
- Skip if any prerequisites are missing; report clearly.
