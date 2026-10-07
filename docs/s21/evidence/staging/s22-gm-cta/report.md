# S22 Staffing & GM deployed proof

Tested 2026-10-06 PDT against `https://app.dealgateapp.com` from branch
`fix/s22-gm-cta`, committed application checkpoint
`9b46d9db0a06f18ea8cac3e1b018512680a6579d` and handoff/deploy checkpoint
`23001678fd65ec0a9e8ba01e06f0a32fbb9fbf38`.

## Deployed revisions

- API: ECS task definition `officeapp-dev-api:87`
- Image: `s22gm-23001678`
- Digest: `sha256:265feaa8a18192e40dceba21fbf46096515f5abb44c4e7246d70676365f3c243`
- Frontend: `assets/index-DYV1BgxV.js`
- CloudFront invalidation: `I9N87XU7RDHU5RX0IG2DPS79L6` (completed)
- Migration task: `f159f3a9db6e4f55a5f7ef6d898e3747` (succeeded)

## Connected proof

Command:

```sh
cd /Users/srikanthparimi/OfficeApp/dealgate-s22-gm-cta/tests/e2e
env AWS_PROFILE=lm-arbiter-poc AWS_PROFILE_STAGING=lm-arbiter-poc \
  AWS_REGION=us-east-2 E2E_BASE_URL=https://app.dealgateapp.com \
  npx playwright test specs/s21/s22-gm-cta-deployed-proof.spec.ts \
  --project=chromium --reporter=line
```

Result: **1 passed** in 2.7 minutes. The fresh browser used a server-issued
fixture and six real Cognito identities. It exercised the deployed SPA, API,
RDS commercial draft/version storage, authoritative Decimal calculation and
approval state machine; no feature response was mocked.

Independent expectation for October 2026: 22 weekdays x 8 paid hours x
USD 30/hour x (2 full allocations + 1 half allocation) = USD 13,200 labor
cost. Against the fixed fee of USD 75,400, gross profit is USD 62,200 and GM
is 82.4933687%. The deployed UI returned USD 75,400 revenue, USD 13,200 cost,
USD 62,200 gross profit and 82.5% displayed GM. Hourly client billing rates
were deliberately null: fixed-fee revenue came from the contract fee.

The sequence proved:

1. An incomplete draft showed known contract revenue and named the exact row
   and field (`Fix row 1 calendar`) rather than generic `Unavailable`.
2. The CTA focused the missing calendar control. Completing both versioned
   calendars produced the independently expected calculation.
3. `Save financial version` persisted the commercial model. A full page
   reload retained the same costs/GM and changed the CTA to
   `Submit for approval`.
4. Confirming the real reviewer plan persisted `pending_delivery_hr`, changed
   the CTA to `View review status`, and refreshed the readiness panel.
5. Teardown deleted the fixture. `scripts/check-test-data-clean.sh` reported
   zero test clients and zero e2e approvers on real SOWs.

## Screenshots

- `01-before-known-revenue-and-row-blocker.png`
- `02-calculated-financials-save-action.png`
- `03-save-reload-submit-action.png`
- `04-transition-persisted-review-status.png`

## Original record (read-only)

Opportunity `bbefb2b0-90fc-4a7c-8995-bbe637b44654` was never mutated. A
post-deploy preview of its existing draft returned known revenue USD 75,400
while cost-derived values stayed null. Its current first blockers are the
missing billing schedule, loaded-cost basis and human cost confirmation. Once
those are supplied, row-specific calendar/rate blockers are surfaced in order.

## Failed-attempt history

- Attempt 1 never created a fixture: the auth helper expected an obsolete
  flat secret shape. The deployed secret uses shared metadata plus nested
  `roles`; the helper now supports both without logging secret values.
- Attempt 2 reached the correct deployed state but the proof locator expected
  `Fix row 1 working calendar`; the actual accessible label is
  `Fix row 1 calendar`. The screenshot showed the behavior was correct, so
  only the test locator changed before the successful run.
