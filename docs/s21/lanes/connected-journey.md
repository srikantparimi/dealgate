# Connected Journey Authoring

Branch `s21/connected-actuals-automation`, base
`8d4e5f43433758010fa5bd0f257bfcbaf2c50788`. Only the new script and this report
are owned. **UNEXECUTED**: no Python, tests, worker, database, provider, browser,
installation or build command was run in this lane. Static contract review is
not runtime verification. Integration lead must review and execute.

## Safety And Prerequisites

The script reuses `s21_real_journey.document` and `OwnedStorage`, including its
dedicated localhost `/s21_journey` database guard and exact S3-key/version
cleanup. HTTP uses actual ASGI application routes. Extraction and signature
verification use real Bedrock; storage is real S3. Only identity is replaced
with uniquely created persisted test users; SES remains the explicit sink.
It does not claim Cognito, delivered email, HubSpot sync, browser or staging.

Lead must provision a fresh `s21-connected-*` tenant in the dedicated migrated
local database and run with exactly that tenant. Do not reuse `s21-lead` or an
existing business/test population. Prerequisites, configured by an authorized
persisted `SystemAdmin` + `officeapp-e2e` identity under that tenant:

- `POST /people/sourcing/rules`: `expected_version_id:null`, unique request key,
  written reason, rules exactly `python/US/30` and `python/India/30` using
  `skill`, `location`, `lead_days` fields.
- `POST /people/sourcing/automation`: `expected_version_id:null`, `enabled:true`,
  `source_scope:"authorized_sources"`, unique request key, written reason.
- No demand sources, people or jobs in that tenant. The script checks this.
  It does not enable/disable/change either rule. The rule creator is explicitly
  included among the new fixture's server-granted participants; no existing
  fixture grant or user is modified. A new, empty managed workforce snapshot
  is imported with this run's unique source identity.
- Lead authorization for the existing helper's real S3 bucket and Bedrock
  credentials, plus current API schema and separate worker code from one tree.

Lead-only proposed command, after provisioning (not executed here):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/api:$PWD" \
S21_CONNECTED_TENANT="s21-connected-<fresh-run>" \
S21_CONNECTED_PROVIDER_CALLS=lead-authorized \
api/.venv/bin/python -B scripts/s21_connected_journey.py
```

`POSTGRES_URL` must already identify the dedicated local database. Preserve
stdout with the lead's evidence tooling and record source/schema/provider
revisions. Fixture data remains for exact-ID DB inspection and immutable
history evidence; the script only deletes its own S3 keys (and their versions).
Those cleaned objects cannot subsequently be re-opened through the retained
fixture. Lead owns eventual exact-ID fixture/database disposal; no broad data
cleanup is performed. Fixture issuance expires, so do not pause and resume a
partly issued fixture beyond its grant validity.

## Verified Contract Blocker

The complete requested Pipeline entry cannot safely be authored as a success
against this baseline. `hubspot_pipeline.py` requires `source == "hubspot"`.
`test_fixtures.create_fixture` issues a `sow_upload` source without external IDs.
`project_source.capture_project_scope` explicitly rejects a granted fixture
with `source == "hubspot"` or a non-null external deal ID as conflicting source
provenance. Changing that field for convenience would bypass the safety model.

The script therefore asserts the fixture Pipeline detail returns 404, emits
the blocked boundary, and continues the real Deal-to-Delivery/Forecast/actuals
and automation chain without modifying source classification. It always emits
`full_journey_passed:false` and `staging_verified:false`. Its successful process
exit only means the explicitly scoped remainder's assertions passed; it never
means the full journey passed. A supported safely classified Pipeline fixture
contract or separately approved real-source testing path remains a lead-owned
dependency. No mocked Pipeline response or synthetic CRM identity is used.

## Independent Assertions

The document explicitly specifies one October assessment, USD 24,000 fee and
USD 10,000 cost: US fee/cost 10,000/4,000, India 14,000/6,000. Seven full-time
Engineers are source facts: two US and five India, with explicit calendars.
The script never derives expected money or headcount from the application
calculator. A hybrid with two fixed-fee children stores those source facts.

Actual application path: server fixture grant, Deal list/detail, real upload
and extraction, field confirmation, canonical commercial save, submission,
five actual function decisions, signed artifact upload/hash/verification,
Delivery acceptance and release. Assert one project with the same package,
GM, SOW, opportunity, account, tenant and fixture-grant lineage. Forecast's
15-month response must contain that exact signed source, USD24,000 signed,
USD10,000 cost and zero potential in October.

Released-project jobs must initially be `review` because skills/level are not
yet published. Source lines must still be exactly 2 US/5 India, not weighted.
Explicit Delivery evidence-backed capability publication then triggers a
separate real worker process. Assert current successful sourcing draft points
to the new publication and the same project/GM source version, preserves prior
incomplete draft/job history, has seven incremental gaps, and September 1
sourcing date (October 1 minus configured 30 calendar days). Another worker
pass must not create a duplicate current draft. This is a signed 100% source;
it does not substitute for the separate 70%-probability Company X scenario.

Same-project actuals use the released project's exact GM basis: recognized
12,000.01, billed 15,000, collected 8,000, cost 6,000. Replay retains one import;
revision2 corrects recognized to 11,000.99 while DB retains both revisions.
Four measures remain distinct, signed forecast rows and frozen project baseline
remain unchanged. This proves attribution, not an unimplemented matched-basis
actual-to-date plus remaining-forecast overlay.

## Coverage Mapping

All mappings are **authored/unexecuted partial assertions**, not scenario or
requirement closures. Existing 51-ID / 45-scenario ledgers are untouched.

| Scenario | v3 requirement IDs | Script scope and remaining coverage |
| --- | --- | --- |
| T05/T06 | S21-05, S21-06 | Exact five-function route and decisions; not OOO/CEO/unauthorized routing matrix. |
| T07 | S21-07, OP-03 | Positive server-granted fixture lineage; not full isolation/invalid historical decisions. |
| T15/T16 | S21-17, S21-18, FC-09 | One real extracted hybrid fixed-fee document through release; not all seven models or adversarial extraction. |
| T17 | S21-02, DG-02, DG-03, DG-04, DG-05, DG-06, CO-05 | Connected Deal onward; Pipeline entry explicitly BLOCKED, no browser/header/agreement/count/leak-gate closure. |
| T18/T19 | FC-01, FC-02, FC-03, FC-04, FC-05 | Same signed source, money, period and 15 months through HTTP; not five views or six-account scenario reconciliation. |
| T21 | S21-15, S21-17, FC-02, FC-04, FC-05, FC-06, CO-05 | Same-project four-basis import/replay/correction and immutable baseline; not full matched-basis overlay/currency/rounding matrix. |
| T22/T23 | FC-07, FC-08 | Full seven-person committed demand, explicit capability publication and sourcing dates; not 70%/part-time/competition/continuity. |
| T24 | FC-09, FC-10 | Review-to-repaired source automation using real worker and idempotent rerun; not disabled-rule/re-extraction/held-out-model suite. |

No T08/OP-02 email delivery claim: SES is a sink and notifications are not
drained by this script. No staging deployment, click-through or main merge.
