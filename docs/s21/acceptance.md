# S21F Acceptance Crosswalk

Current execution ledger: [progress-20261002.md](progress-20261002.md).
12 passed locally,0 currently failed,25 pending,8 blocked=45.
The `not_run` specification labels below predate partial executions; consult
the current ledger and evidence rather than treating these as45 absent tests.

These are test specifications, not executed or skipped tests. Preserve all 45 unique scenario IDs. Prefix legacy S20 tests with `S20:`; never confuse S21F:T44 (BU) with S20:t44-full-journey.

Each scenario uses the exact independent observable assertions below. Browser cases belong in `tests/e2e/specs/s21-forecast/<area>.spec.ts`; service/DB/fault cases in `api/tests/s21_acceptance/test_<area>.py`, extending attributable existing tests where suitable. Planned names are targets, not a claim those files exist. QA must record actual collected node IDs before marking executed. T33-T38/T42 additionally require operational evidence scripts/human steps, not pretend unit equivalents.

Run records include expected, collected, executed, passed, failed, skipped, xfailed and not-run counts plus every exception reason. Include run ID, exact source/frontend/API/worker/schema versions, fixture/role/environment, command, expected/actual, traces/screenshots/logs and remaining risks. Do not weaken assertions or use retries to green. Mocking external provider faults is allowed only in isolated tests, with separate live contracts; feature API responses are real.

## S21F:T01

Requirements: S21-01, DG-05, CO-09. Area: `deletion`. Status: **not_run**.

Delete separate SOW fixtures at draft, submitted, review, approved, signed and handed-off states. Verify database/object cleanup, all count surfaces and a fresh upload. Preserve parent/client agreements, other SOWs and a project containing actuals. Inject late callbacks and retries; no resurrection or remaining active reminder.

## S21F:T02

Requirements: S21-02, DG-06. Area: `workspace`. Status: **passed (local)**.

Browser37810 at39f157505c2904dd8e75a86c5f8d3b0e4eb8cc0b; [all assertions and boundaries](evidence/baseline/t02-workspace.md). Staging remains unverified.

From Overview click Staffing & GM, then Approvals and Back. Header, tabs, selected SOW/version and exactly one readiness panel stay visible. Deep-link and reload select the same tab.

## S21F:T03

Requirements: S21-03, DG-06. Area: `workspace`. Status: **not_run**.

Upload, edit scope, navigate forward/back and reload. Values persist. After submission, edit pricing; a new draft appears, old document/decisions remain immutable and resubmission invalidates stale approval authority.

## S21F:T04

Requirements: S21-04. Area: `workspace`. Status: **not_run**.

Exercise empty CRM owner, unresolved owner metadata, missing year and ambiguous pricing. Show distinct honest states and local editors. Correct values and reload; no hidden hash or fabricated year/uploader-as-CRM-owner.

## S21F:T05

Requirements: S21-05. Area: `routing`. Status: **passed_local**.

Browser89032 at a5ee76d; [four conditions, database proof and boundaries](evidence/baseline/t05-reviewer-plan.md). Staging unverified.

Skip reviewer selection in an earlier step, open Approvals, see planned functions and eligible names, edit a permitted reviewer and submit. Invalid or unauthorized reviewer IDs are rejected server-side.

## S21F:T06

Requirements: S21-06. Area: `routing`. Status: **not_run**.

Resolve Shawnna outside OOO, Srikanth inside the configured window and Shawnna after it. Check timezone boundaries, inactive fallback and in-flight reassignment. Normal GM omits conditional CEO review; breached GM requires Al; incomplete costing blocks assessment.

## S21F:T07

Requirements: S21-07, OP-03. Area: `test_isolation`. Status: **not_run**.

Try to route, execute, decide and notify a real SOW with a test identity. All are rejected. A forged run tag cannot bypass controls. Repair a contaminated pending task and retain its audit trail. Validate the separate handling of already-recorded invalid decisions.

## S21F:T08

Requirements: S21-08, OP-02. Area: `mail`. Status: **not_run**.

Submit a valid safe-test SOW. Verify real outbox → worker → test mail/provider flow and proper recipient resolution. Inject rejection, timeout and retry; show delivery status, one intended notification and recoverable failures. Confirm SES account/region separately; include T33 to T37 for rollout readiness.

## S21F:T09

Requirements: S21-09, S21-11, DG-03. Area: `pipeline`. Status: **passed (local)**.

Evidence: [filtered Pipeline proof](evidence/baseline/t09-filtered-pipeline.md),
browser62013 at508c450 with real private PostgreSQL, exact CSV and response-race
assertions; ownership-verified private database cleanup. Not staging/source parity.

Seed disjoint owners/BUs/stages across three pages. Click chips and combine filters. Verify exact row membership, client matching count, summaries and all-page export. Remove one chip, reload, Back and saved view. Zero matches stays zero; delay an old response to prove it cannot overwrite the new selection.

## S21F:T10

Requirements: S21-04, S21-10, S21-12, DG-02, CO-08. Area: `source_parity`. Status: **not_run**.

Compare every displayed CRM field to an authorized source snapshot, including owner with no DealGate login, pipeline label and real BU mapping. Company and deal ownership flags remain independent. Required identity labels show names across breadcrumbs, details, tables, search and export; legitimate numeric amounts remain valid.

## S21F:T11

Requirements: S21-13. Area: `tracking`. Status: **passed (local)** (43442/1441649 and durable PG69943). [Evidence](evidence/baseline/t11-tracking.md). Staging remains unverified.

Add/edit/pin a comment and create/edit/complete an action from the deal page. Reload and inspect latest activity. Check another role, unauthorized edits and simultaneous updates. CRM notes remain read-only and separately attributed.

## S21F:T12

Requirements: S21-14, DG-01, CO-03. Area: `tracking`. Status: **not_run**.

Configure a per-user alert; trigger its event through the application. Change due date, complete action, disable rule and replay delivery. Obsolete reminders cancel and no duplicates send. Saved-rule groups update; manual watchlists do not change unexpectedly or leak inaccessible records.

## S21F:T13

Requirements: S21-15, S21-17. Area: `calendar`. Status: **passed (local)**.

Evidence: [calendar proof](evidence/baseline/t13-calendar.md), browser41842 at
00371d2 (applicationbde6d29),78 focused independent oracle tests. Not staging.

Use the independent ten-person calendar oracle and partial-month/part-time/mixed-location cases. Verify scheduled, billable and paid hours, monthly cost/revenue/GM and holiday details. Missing calendars/costs remain unresolved; no mandatory manual aggregate hours.

## S21F:T14

Requirements: S21-16. Area: `amendments`. Status: **not_run**.

Create extension with rate/headcount/term changes. Pending amendment leaves original active. Complete required approvals/signature and verify effective schedule, Project term, renewal alerts and continuing team. Test nonrenewal, overlapping periods and a late callback.

## S21F:T15

Requirements: S21-17, S21-18. Area: `pricing_profiles`. Status: **not_run**.

For each pricing profile, upload a real fixture file through the UI, inspect evidence, correct extraction, save/reload, calculate, approve, sign in sandbox and hand off. Include fixed assignment, recurring MSP, staffing, T&M, milestone, unit/story point and hybrid.

## S21F:T16

Requirements: S21-17, S21-18, FC-09. Area: `extraction`. Status: **not_run**.

Use scans, conflicting totals/dates, missing year, missing currency, unsupported pricing and embedded hostile instructions. Extraction preserves the upload, flags exceptions and never changes reviewers or policies. Re-extraction keeps manual corrections until reviewed.

## S21F:T17

Requirements: S21-02, DG-02, DG-03, DG-04, DG-05, DG-06, CO-05. Area: `journey`. Status: **not_run**.

DG-02 through DG-06: Pipeline → client → named deal with no SOW → Upload SOW → confirmation → complete workspace → signature → handoff. Verify NDA/MSA presence semantics, no stub/delete/readiness before upload, one project after repeated handoff events, clear gates, correct names and consistent open-deal counts. Run the existing test-data leak gate and route inventory as part of this journey.

## S21F:T18

Requirements: FC-01, FC-02, FC-03, FC-04. Area: `forecast_views`. Status: **passed_local**.

Evidence: [T18 connected controls and failure history](evidence/baseline/t18-five-views.md),
final anchor proof8316 atad30e779c7adb6f48e230846612ac4cb35ad1fdb.
All six original conditions asserted locally; staging and parent remainders remain.

Open all five Forecast views using persisted data. Filter and drill company → account → SOW/opportunity → monthly detail. Preserve scope/period/scenario and show current quarter separately from future totals. Verify names, empty/error states and all controls perform an action.

## S21F:T19

Requirements: FC-02, FC-03, FC-04, FC-05. Area: `forecast_oracles`. Status: **passed_local**.

Evidence: app44fec5163c722e87eaeb69f0c486ce32a875d4c0, independent matrix25684,
connected browser54224 and QA-strengthened final reconciliation93529.
[Conditions](scenario-conditions.md#s21ft19---financial-oracles), [proof/history](lanes/t19-plan-terms.md).
Staging unverified; no parent requirement completion inferred.

Load the independent Company X fixture and the accepted six-account preview fixture. Verify signed, Expected and Upside per month/quarter, account sums and company totals. Change date/value/probability and reload; all affected views reconcile.

## S21F:T20

Requirements: S21-16, FC-05, FC-08. Area: `forecast_dedupe`. Status: **not_run**.

Link a forecast to a CRM deal, convert it to one signed SOW, then repeat sync. Contract replaces potential once. Test partial conversion, two SOWs under one deal, lost deals, duplicates, alternative options and amendments without double counting.

## S21F:T21

Requirements: S21-15, S21-17, FC-02, FC-04, FC-05, FC-06, CO-05. Area: `actuals`. Status: **passed_local**.

Test zero/unknown revenue, incomplete cost, mixed currencies, fixed-fee allocation, milestones and rounding conservation. Import actuals twice, apply a correction and combine only matched actual-to-date with uncovered forecast. Billed amounts never become recognized revenue silently.

T21.07 financial workflow76926 plus same-identity PG11028 and current/replay/
responsive33980 at19ca6f7 close the remaining condition; prior .01-.06/.08
evidence retained. [Proof and failure history](evidence/baseline/t21-coverage.md).
Seeded signed prerequisite/local identity; no new signature or staging proof.

## S21F:T22

Requirements: FC-07. Area: `people`. Status: **passed_local**.

Browser84625/e879213 plus current27 targeted capacity/CompanyX cases96252;
[all seven conditions and evidence boundaries](evidence/baseline/t22-part-time.md).

Show the full Company X team of 2 onshore and 5 offshore at 70% probability. Change the scenario; headcount remains seven. Two overlapping opportunities compete for one available person; no double match. Check part-time capacity, roll-off, continuing teams and sourcing dates.

## S21F:T23

Requirements: FC-07, FC-08. Area: `people`. Status: **passed_local**.

Admin88901/Sales49160 at23dffd9 plus44tests74987 and prior94568 worker replay;
[all six conditions and boundaries](evidence/baseline/t23-publication.md).

Publish forecast demand to the actual People/recruitment view; prepare a sourcing draft, change start/headcount and see the update. Repeated events do not create duplicate requests. Restricted users cannot view costs or reserve/hire through a planning endpoint.

## S21F:T24

Requirements: FC-09, FC-10. Area: `automation`. Status: **not_run**.

Run a fixture SOW/findings through extraction, plan preparation, exception review and auto-refresh. Disable a rule and prove the worker honors it. Re-upload/retry/re-extract without duplicate plans or lost overrides. Evaluate a held-out live-model sample separately.

## S21F:T25

Requirements: FC-11, FC-12. Area: `exports`. Status: **not_run**.

Export all authorized rows and reconcile to the screen and API at the same snapshot. Test historical forecast snapshots, stale events, concurrent edits and tenant/role boundaries, including aggregates, deep links and CSV fields.

## S21F:T26

Requirements: S21-02, S21-11, DG-03, FC-01. Area: `accessibility`. Status: **not_run**.

keyboard navigation, form labels, focus return after dialogs, validation errors, browser Back, loading/error/retry states, long names, zero data and desktop/mobile layouts. Tables may scroll within their container; the page must not overflow. Verify the actual screen and navigation, including controls outside table cells.

## S21F:T27

Requirements: S21-10, FC-12, CO-07. Area: `sync_failures`. Status: **not_run**.

CRM 429/timeout, expired access and duplicate/out-of-order webhooks: retry and reconcile without data loss, duplicate records or misleading freshness.

## S21F:T28

Requirements: S21-01, S21-03, DG-04, FC-10, FC-12, CO-07, CO-09. Area: `recovery`. Status: **not_run**.

Worker restart between commit and event handling, duplicate upload/submit/handoff, storage failure and stale callback: one business result, visible retry state and no resurrection.

## S21F:T29

Requirements: S21-18, FC-12, CO-07. Area: `migration`. Status: **not_run**.

Migrate a representative database, interrupt backfill and resume. Verify foreign keys, row counts, legacy model coverage, no lost agreements/actuals and a tested rollback/restore.

## S21F:T30

Requirements: S21-16, CO-05, CO-10. Area: `staging_journey`. Status: **not_run**.

Run the complete Company X journey plus one staffing extension and one deletion on the combined staging revision. Prove every integration boundary, resource update and aggregate reconciliation.

## S21F:T31

Requirements: S21-09, S21-11, FC-12. Area: `performance`. Status: **not_run**.

Measure list/filter/summary/export behavior at the declared representative load. Verify pagination correctness, no per-row external API calls, bounded query counts and documented latency.

## S21F:T32

Requirements: S21-01, S21-05, S21-07, S21-13, FC-11, FC-12, CO-09. Area: `authorization`. Status: **not_run**.

Attempt unauthorized direct API edits, cross-account/tenant reads, cost-field access, forged test tags and reviewer bypass. Check audit and refusal; no data leakage through counts or exports.

## S21F:T33

Requirements: OP-01, CO-06. Area: `infrastructure`. Status: **not_run**.

Fresh Terraform plan identifies the correct account/region/state and exact resource diff. Approval matches the applied changes. In an isolated test, a sync stall triggers the intended alarm and destination; processing recovery clears it. Prove heartbeat/missing-data behavior and no false incident from a quiet CRM.

## S21F:T34

Requirements: S21-08, OP-02. Area: `mail_readiness`. Status: **not_run**.

Verify readiness for all six roster addresses by domain or individual identity in the sending region. Distinguish identity created, verified, reviewer eligible, queued, accepted and delivered. No duplicate verification sends on routine deploy; an authorized delivery check reaches the intended recipient.

## S21F:T35

Requirements: S21-06, S21-07, OP-03. Area: `liberty`. Status: **not_run**.

Inspect and repair the precise contaminated Liberty cycle. Preserve the SOW/version and history, reject old tasks/callbacks, preview real reviewers and resubmit once. Verify one new cycle and correct tasks/notifications. Exercise destructive/failure paths on an isolated fixture before any live remediation.

## S21F:T36

Requirements: OP-04, CO-06, CO-08, CO-10. Area: `canary`. Status: **not_run**.

A human saves a named canary in HubSpot. Normal sync makes its complete record visible in DealGate within 120 seconds. Verify update propagation, filtering/counts and no SOW stub. Record t0/t1, source fields, revisions and cleanup/reconciliation; no manual sync shortcut.

## S21F:T37

Requirements: OP-05. Area: `ses_production`. Status: **not_run**.

Prepare and submit the truthful SES production-access request through the approved workflow. Verify actual outcome, quotas, sender configuration, bounce/complaint handling and controlled delivery after approval. Pending/denied remains a reported dependency; no false green.

## S21F:T38

Requirements: CO-01, CO-02. Area: `baseline`. Status: **not_run**.

Resolve full main SHA, release tag, actual image/digest, stable service and check-only smoke. Reconcile every legacy row, T32/T34 and FINAL-T38. Verify local/staging test selection and complete run counts; no unsupported “all green” or skipped failure.

## S21F:T39

Requirements: S21-09, S21-14, DG-01, CO-03. Area: `watching`. Status: **passed (local)**.

Browser46207 at941953ab65d3621224906a5bdbe554fd09daa9aa; [all assertions and boundaries](evidence/baseline/t39-watching.md). Staging remains unverified.

Empty Watching card shows 0. One watched deal in three groups yields exactly one matching row and total across card and list. Unwatch returns 0. Assert identities and access filtering, not only numeric formatting.

## S21F:T40

Requirements: S21-09, CO-04. Area: `approval_card`. Status: **passed (local)**.

Browser99369 at205d51aadec743eb613fdb3ceb184520eacb79bb; [all assertions, snapshot fencing and boundaries](evidence/baseline/t40-approval-card.md). Staging remains unverified.

Mixed review fixture proves distinct in-review SOW package count equals the approvals destination and exact membership. Multiple reviewers do not multiply one SOW; two SOWs under one deal remain two.

## S21F:T41

Requirements: DG-06, FC-06, CO-05. Area: `journey`. Status: **not_run**.

Execute the formerly skipped legacy full journey through matching signed upload, release, delivery acceptance, one project and known monthly actuals/GM. Reject wrong versions/signatories; retries stay singular. Teardown leaves no leaks.

## S21F:T42

Requirements: OP-01, OP-04, CO-06. Area: `consumer`. Status: **not_run**.

Prove reviewed drift adoption, approved apply and real consumer processing with lag evidence. Exercise stalled/quiet/recovery states and alarm delivery. Link the normal-sync human canary T36; a running task alone does not prove freshness.

## S21F:T43

Requirements: CO-07. Area: `backfill_chaos`. Status: **not_run**.

Rename stage/reassociate source records; verify labels and membership. Interrupt backfill at checkpoint/commit boundaries, resume the same generation and prove complete exact-once effects, no false deletion and safe duplicate/out-of-order processing.

## S21F:T44

Requirements: S21-12, CO-08. Area: `business_unit`. Status: **not_run**.

Exercise configured, absent, empty and inaccessible BU metadata. Correct display/filter behavior persists on reload; mapped values drive account/company grouping. Record current live property availability separately from synthetic adapter coverage.

## S21F:T45

Requirements: S21-01, CO-09. Area: `cleanup`. Status: **not_run**.

Test aged tagged fixture, young active fixture, untagged local client, mirrored client and real-name collision. Only authorized eligible targets disappear. Zero-age mode is scoped; failures/retries preserve unrelated records and financial history.

## Independent Financial Fixtures

A: Company X signed October assessment USD 24,000; separate Nov 2026-Apr 2027 fixed assignment USD 420,000 revenue / 210,000 cost, explicitly even six-month service allocation, 70% probability. Monthly full/weighted revenue 70,000/49,000. Q4 Expected 122,000; Q1 147,000; Q2 49,000; next two full quarters 196,000; whole proposed term weighted 294,000 revenue / 147,000 cost, GM 50%. Team remains 2 US + 5 offshore. Shift to December preserves total fee.

B: inclusive Oct 1 2026-Jul 31 2027, ten people, Mon-Fri, 8h/day, 100% allocation, contract's ten synthetic paid/nonbillable holidays. Independent monthly billable days 21,19,22,19,19,23,22,20,21,21 (207); paid days 217; billable hours 16,560; paid hours 17,360; USD100 billed and USD60 paid cost -> revenue 1,656,000; cost 1,041,600; GM approximately 37.10145%. Independently enumerate dates outside production code.

C: Separate approved HTML six-account fixture: October signed 208,500; Q4 Expected 700,700; Q1 449,400; Q2 217,000; future Expected 666,400, signed 174,000 and Upside 894,400. Production never inherits these dates/rates/calendar assumptions.

Performance fixture: at least 10,000 deals, 1,000 SOWs, 24 buckets or larger actual scale; p95 lists <=2s, summaries <=3s. State hardware/concurrency and report misses as failures. Migration fixtures exercise interrupted resume, malformed data, concurrent writes, foreign keys and restore, not only an empty schema.
