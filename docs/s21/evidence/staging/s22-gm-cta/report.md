# S22 simplified Staffing & GM deployed proof

Tested 2026-10-07 PDT against `https://app.dealgateapp.com` from branch
`fix/s22-gm-cta`, application checkpoint
`5cd52ea490729227b380988288455273e9282684` and pre-deploy documentation
checkpoint `0b5a04620b29c9339d65a0a62029bb8d5efd937c`.

## Deployed revisions

- API: ECS task definition `officeapp-dev-api:89`, rollout completed 1/1
- Image: `s22confirm-5cd52ea`
- Digest: `sha256:a037c926b3b0691ed5209e6f96c6b9bde7cf3b8c6c4ee428caff772d3338d111`
- Frontend: `assets/index-NGaZkXeJ.js`, CSS `assets/index-CGMBFthR.css`
- CloudFront invalidation: `I4P250ECLXKHD7DMFHW619SM02` (completed)
- Migration task: `c7b7207dc72d435ca1c67b3e5eabbd3b` (succeeded)
- Deploy smoke: `smoke 20261007T175159Z` (green; cleanup gate clean)

## Connected proof

Command:

```sh
cd /Users/srikanthparimi/OfficeApp/dealgate-s22-gm-cta/tests/e2e
env AWS_PROFILE=lm-arbiter-poc AWS_PROFILE_STAGING=lm-arbiter-poc \
  AWS_REGION=us-east-2 E2E_BASE_URL=https://app.dealgateapp.com \
  npx playwright test specs/s21/s22-gm-cta-deployed-proof.spec.ts \
  --project=chromium
```

Result: **1 passed in 2.0 minutes**. The fresh browser used a server-issued
fixture and six real Cognito identities. It exercised the deployed SPA, API,
RDS draft/version storage, authoritative Decimal calculation and approval
state machine; no feature response was mocked.

The fixture deliberately contained the reported legacy failure shape: row 1
had a seven-day calendar shell with all 21 scheduled/billable/paid values set
to empty strings. The deployed editor discarded that unusable shell before
preview. It displayed the compact staffing table and one actionable
`Fix row 1 hours` CTA; it did not expose a Pydantic validation dump, calendar
editor, Cost basis, Monthly plan or Review & save section.

Independent expectation: each row had 176 per-person hours at USD 30/hour.
Row 1 had two people at 100% allocation and row 2 had one person at 50%, so
labor cost is `176 x 30 x (2 + 0.5) = USD 13,200`. A USD 2,500 Travel cost
makes total delivery cost USD 15,700. Against the USD 75,400 fixed fee, gross
profit is USD 59,700 and GM is 79.1777188%. The deployed UI displayed USD
75,400 revenue, USD 13,200 labor, USD 2,500 direct costs, USD 15,700 total
cost, USD 59,700 gross profit and 79.2% GM. Hourly client bill rates remained
absent; fixed-fee revenue came from the contract fee.

The sequence proved:

1. The empty legacy calendar became one precise row-level Hours blocker.
2. The workspace CTA focused `Hours 1` instead of navigating back to the same
   screen.
3. Entering both Hours values and the additional cost produced the independent
   financial expectation through the server calculation service.
4. The primary action changed to `Save`; saving opened `Confirm SOW` rather
   than exposing approval submission inside Staffing & GM.
5. Confirm SOW showed term start/end, the saved 79.2% GM, Delivery, HR,
   Finance and Legal, and `CEO exception — Not required`; a full reload
   preserved those values.
6. `Complete scope` navigated to Approvals. Confirming the real reviewer plan
   persisted the review state and displayed approved/pending/queued pipeline
   status rather than looping back to Staffing & GM.
7. Teardown deleted the fixture; `scripts/check-test-data-clean.sh` reported
   zero test clients and zero e2e approvers on real SOWs.

## Screenshots

- `01-before-known-revenue-and-row-blocker.png`
- `02-calculated-financials-save-action.png`
- `03-confirm-sow-dates-gm-and-approval-path.png`
- `04-approvals-pipeline-status.png`

## Original record

Opportunity `bbefb2b0-90fc-4a7c-8995-bbe637b44654` remained read-only. The
deployed proof used an isolated equivalent fixture for every mutation.

## Diagnostic history

- The first refreshed connected run reached the correct confirmation page but
  stopped because the sample document extracted `signatories.value=null`; the
  proof had incorrectly treated null as a valid confirmed signatory. Its trace
  showed dates, complete GM and staffing intact. The fixture was deleted, the
  proof was corrected to supply an explicit client signatory, and the one
  relevant rerun passed.

- The 2026-10-06 proof covered the older full-calendar workflow on API
  revision 87 and is superseded by this report and the refreshed screenshots.
- Before the compatibility fix, the new focused regression reproduced the
  defect: preview received the legacy calendar with 21 blank decimal strings.
  After `e92b4dd`, the same regression passed with `calendar:null` and a simple
  missing-Hours state.
- The first image-build command used `api/` as context and failed before push
  because the Dockerfile copies root-relative `api/` and `worker/` paths. The
  corrected `-f api/Dockerfile .` build produced the deployed image above.
- The first SPA publication manually supplied the Cognito domain without an
  `https://` scheme. An unauthenticated browser therefore resolved the hosted
  UI as a relative app path, repeatedly prefixed it and reached CloudFront 414.
  The first emergency rebuild corrected the domain but also exposed that the
  manually overridden redirect URI `/` was not in Cognito's callback list.
  The final bundle was built from the checked-in host-agnostic
  `web/.env.production`: fresh navigation reaches Cognito over HTTPS with
  `/auth/callback`, and a real hosted-UI login returns to `/command` with the
  DealGate shell visible.
