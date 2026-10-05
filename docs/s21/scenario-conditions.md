# S21F Scenario Conditions

Incremental evidence reconciliation, updated 2026-10-03 19:07 UTC. Source specification:
[acceptance.md](acceptance.md), all **45 original S21F scenarios**, unchanged.
Original inventory cutoff was `6591859e57d14ba94b8a62b3d4c735932bdb391c`;
changed rows now cite their later attributable executions. Latest T18 application
is `ad30e779c7adb6f48e230846612ac4cb35ad1fdb`; earlier financial/navigation
evidence is on fa0c787 and remains bounded to those unchanged behaviors. The earlier OCR
red checkpoint `3044163` is superseded by the focused implementation and tests at
`3a754550da58da1cf941195a016e2f4d8778489b`.

Each numbered condition below comes from the original scenario prose. Splitting
conditions does not create new scenario IDs or reduce a scenario's scope.
Where the source requires a matrix (six deletion states, seven pricing profiles,
all views/roles), the matrix remains explicit; one passing member is not all.

Tags: **verified(local)** means the cited recorded execution establishes the
stated bounded condition at the stated layer; **verified(staging)** requires
matching deployed evidence (none identified here). **implemented-unverified**
means an implementation/bounded related proof exists, but this exact condition
or its required matrix/journey is not established. It does not certify complete
implementation. **missing** identifies an explicitly outstanding implementation
or required evaluation artifact, not merely an old test name. **blocked** names
an external/deployment/human dependency. No verified condition closes its parent
scenario, requirement, release gate or PO acceptance. Older reports' red findings
are not treated as current defects where the ledger records their remediation.

Evidence keys are linked at the end. `[P]` identifies the exact requirement row
or scenario grouping in the current ledger, not a blanket suite equivalence.
Aggregate pass counts and test filenames alone never establish a condition.
T39 delta at `941953ab65d3621224906a5bdbe554fd09daa9aa`: browser46207
passed all five original conditions with real API/PostgreSQL; affected API53674
passed54. [T39 evidence and historical failure](evidence/baseline/t39-watching.md).
This supersedes browser6428's readiness failure, not other scenarios' evidence.

T02 delta at39f1575: browser37810 passes all five original navigation conditions;
[T02 evidence](evidence/baseline/t02-workspace.md). No application repair needed.

T40 delta at205d51a: browser99369 passes all original conditions and stale-revision
recovery; [T40 evidence](evidence/baseline/t40-approval-card.md).

Condition inventory: **255 unique conditions across 45 scenarios**: 118
verified(local), 5 verified(staging), 106 implemented-unverified, 2 missing,
24 blocked. These are not equally weighted completion units or an acceptance
percentage. A condition with local component proof can still require the
scenario's connected/staging execution. T39/T02/T40/T13/T09/T11 passed locally; all staging scopes remain open.

## S21F:T01 - Deletion

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T01.01 Delete separate draft, submitted, review, approved, signed and handed-off SOW fixtures. | implemented-unverified | [P] S21-01 explicitly leaves the all-stage matrix open; no six-state proof identified. |
| T01.02 Remove owned database rows and all owned object versions. | verified(local) | [H] Latest Evidence, 1925e81f: real API/PG/separate worker/S3, three jobs done and exact versions removed; bounded parent/child deletion path, not the six-state matrix. |
| T01.03 Reconcile every count surface after deletion. | implemented-unverified | [P] T01/S21-01; full count/UI reconciliation outstanding. |
| T01.04 Fresh upload works after deletion. | implemented-unverified | [P] S21-01/T01; not asserted by object removal alone. |
| T01.05 Preserve parent/client agreements and sibling SOWs. | implemented-unverified | [P] DG-05/S21-01; [PC] shared agreement-key control is narrower than this full standalone SOW matrix. |
| T01.06 Preserve a project containing actuals and its financial facts. | verified(local) | [PC] real service reads retain 36924.125 and legacy facts/baseline; [H] 1925e81f retains project plus 24680.125. |
| T01.07 Late callbacks cannot resurrect deleted source state. | implemented-unverified | [P] S21-01 leaves late callback/key races open; existing fences alone are not the complete injection matrix. |
| T01.08 Retries remain singular and no active reminder survives. | implemented-unverified | [PC] original pending-job replay is bounded; [P] T01/28 still require end-to-end retry/reminder assertions. |

## S21F:T02 - Workspace Navigation

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T02.01 Overview -> Staffing & GM -> Approvals -> Back works. | verified(local) | Browser37810/39f1575 asserts each tab and both Back transitions; T02 evidence above. |
| T02.02 Header and tabs remain visible throughout. | verified(local) | Same run: heading and relevant tabs visible at every stop. |
| T02.03 Selected SOW/version remains consistent. | verified(local) | Same run: version label/current exact API identity every stop; full version unchanged afterward. |
| T02.04 Exactly one readiness panel remains visible. | verified(local) | Same run: count1 and visibility at every stop. |
| T02.05 Deep link and reload select the same tab. | verified(local) | Same run: direct Approvals entry and reload preserve selected tab and shell. |

## S21F:T03 - Revision Persistence

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T03.01 Upload, edit scope, navigate forward/back and reload without losing values. | implemented-unverified | [P] S21-03; connected upload [J] does not assert this full browser sequence. |
| T03.02 Editing pricing after submission creates a new draft. | implemented-unverified | [P] S21-03 leaves post-approval pricing/new-draft workflow open. |
| T03.03 Old document and decisions remain immutable. | implemented-unverified | [P] immutable version/confirmation guards have bounded tests; full pricing-change scenario remains open. |
| T03.04 Resubmission invalidates stale approval authority. | implemented-unverified | [P] S21-03/T28; confirmation locks do not substitute for reapproval lifecycle proof. |

## S21F:T04 - Honest Missing Inputs

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T04.01 Empty CRM owner and unresolved owner metadata are distinct honest states. | implemented-unverified | [P] S21-04/10: source facts exist; every displayed state remains to reconcile. |
| T04.02 Missing year is unresolved, never fabricated. | implemented-unverified | [P] S21-04/18; held-out missing-year originals not established. |
| T04.03 Ambiguous pricing is distinct and has a local editor. | implemented-unverified | [H] unsupported replacement is tested, but unsupported is not equivalent to all ambiguous-price cases. |
| T04.04 Correct each value and retain it on reload. | implemented-unverified | [P] S21-04; complete missing-input matrix not proved. |
| T04.05 No hidden hash or uploader substituted for CRM owner appears. | implemented-unverified | [P] S21-04/10/12; field/surface parity remains open. |

## S21F:T05 - Reviewer Preview

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T05.01 Skipping earlier reviewer selection still yields planned functions and eligible names in Approvals. | verified(local) | Browser89032/a5ee76d direct Approvals, exact five functions/names/defaults; [proof](evidence/baseline/t05-reviewer-plan.md). |
| T05.02 Permitted reviewer can be edited and submission succeeds. | verified(local) | Browser89032 changes Delivery, submits201, reloads; real PG exact frozen versions/five assignments/three task owners; [proof](evidence/baseline/t05-reviewer-plan.md). |
| T05.03 Invalid reviewer IDs are rejected server-side. | verified(local) | [P] S21-05 attributes invalid/stale reviewer guards to 7b0ec21 and its local routing evidence. |
| T05.04 Unauthorized reviewer IDs are rejected server-side. | verified(local) | [P] S21-05/07, 7b0ec21/bd22cb7 containment; real-roster deployment remains outside local scope. |

## S21F:T06 - Roster And OOO

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T06.01 Resolve Shawnna outside OOO, Srikanth inside, then Shawnna after the window. | implemented-unverified | [P] S21-06: exact roster/window proof outstanding. |
| T06.02 Apply the configured timezone at OOO boundaries. | implemented-unverified | [P] S21-06; no exact dated-boundary execution identified. |
| T06.03 Reject inactive fallback and handle in-flight reassignment correctly. | implemented-unverified | [P] S21-06 explicitly leaves both behaviors open. |
| T06.04 Normal GM omits conditional CEO review. | implemented-unverified | [P]/[G] inherited policy coverage exists; exact roster/routing scenario not established. |
| T06.05 Breached GM requires Al. | implemented-unverified | [CM] child-floor checks verify CEO requirement, not Al's current roster identity. |
| T06.06 Incomplete costing blocks assessment. | verified(local) | [CM] independent seven-profile missing-cost checks pass; [P] precision/consumer fixes integrated, not whole OOO proof. |

## S21F:T07 - Test Isolation And Repair

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T07.01 Test identities cannot route or execute real-SOW approval work. | verified(local) | [P] S21-07: bd22cb7 repairs independent legacy-task/containment cases; 130 affected plus 13 independent cases. |
| T07.02 Test identities cannot decide real-SOW approvals. | verified(local) | [O] CEO reproducer plus [P] bd22cb7 remediation/reverification. |
| T07.03 Test identities cannot receive real-SOW approval notifications. | verified(local) | [O] queue and dispatch reproductions plus [P] same repaired independent cases; isolated provider boundary. |
| T07.04 Forged run tags cannot bypass controls. | implemented-unverified | [P] trusted issuance exists; complete attempted tag-bypass path not established by names of tests. |
| T07.05 Repair a contaminated pending task while preserving audit. | verified(local) | 225f627 `approval_remediation.repair_pending_assignment` + `/admin/approvals/{id}/repair-assignment`: reassigns in place, reassigned task + fresh task, no state advance, audit chain verified. Refuses once a decision is recorded. Staging exercise remains. |
| T07.06 Handle already-recorded invalid decisions separately. | verified(local) | 225f627 `quarantine_recorded_decision` + endpoint: immutable Approval rows preserved, package voided with explicit quarantine reason naming the rows, legitimate decisions refused, released packages escalated to OP-03. Permission tests 403 non-admin. Staging exercise remains. |

## S21F:T08 - Mail Flow

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T08.01 Submit valid safe-test SOW and traverse real outbox -> worker -> provider/inbox. | blocked | [P] S21-08/OP-02/05: local SES sink is not real delivery; approved identity/delivery workflow needed. |
| T08.02 Resolve the correct actual recipients. | blocked | [P] OP-02: six exact identities and application eligibility need verification. |
| T08.03 Rejection, timeout and retry expose recoverable delivery status. | implemented-unverified | [P] notification implementations/tests exist; complete fault/status journey not established. |
| T08.04 Send one intended notification, with no duplicate retry send. | implemented-unverified | [P] S21-08/14; no live end-to-end dedup proof. |
| T08.05 Confirm SES account/region and T33-T37 rollout prerequisites. | blocked | [P] OP rows; operational prerequisites remain unsatisfied, not waived by local submission. |

## S21F:T09 - One Filtered Population

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T09.01 Disjoint owners/BUs/stages span three pages with exact membership. | verified(local) | [T09](evidence/baseline/t09-filtered-pipeline.md),62013/508c450:88 independent synthetic CRM deals, positive configured BU, selected64 exact IDs across25+25+14. |
| T09.02 Chips and combined filters reconcile rows, client counts and summaries. | verified(local) | Same browser/API proof:64 deals/16 matching clients/USD64000, exact identities and stage chip/count/value. No feature-response mocks. |
| T09.03 All-page export matches that same filtered population. | verified(local) | Same browser downloads/parses all64 exact deals from page3; independent amounts and total. Older224f7f7 separately proves1002-row concurrent export snapshot. |
| T09.04 Removing one chip preserves the others. | verified(local) | Same browser removes BU only, owner/stage persist,72 deals and exact independent API membership/totals. |
| T09.05 Reload, Back and saved view preserve the selected filters. | verified(local) | Same browser page3 reload/Back exact IDs; saved stage-only view clears omitted stale owner/BU and applies saved sort, reload preserves8 exact deals. |
| T09.06 Zero matches remains zero, without unrelated clients. | verified(local) | Same browser/API zero selection has0 deals/0 matching clients/empty totals; client-display option also exports zero deals without400. |
| T09.07 A delayed old response cannot replace a newer selection. | verified(local) | Same browser delays genuine10-deal/3-client/USD10000 responses, verifies those payloads, releases after new0 selection; successful completion leaves exact0 rows/clients/summary. |

## S21F:T10 - Source And Name Parity

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T10.01 Every displayed CRM field equals an authorized source snapshot. | implemented-unverified | [P] S21-10/12: adapters/PG checks exist, every reader and real source parity remain open. |
| T10.02 Owner without DealGate login still shows authoritative identity. | implemented-unverified | [P] S21-10: adapter exists, connected display coverage remains. |
| T10.03 Pipeline label and actual configured BU mapping match source. | implemented-unverified | [P] S21-12/CO-08: source observation and facets tested, live parity not established. |
| T10.04 Company/deal ownership flags remain independent. | implemented-unverified | [P] S21-10: distinct model/adapter axes exist; all-surface scenario remains open. |
| T10.05 Breadcrumbs, details, tables, search and export show required names. | implemented-unverified | [J] names on the local bound path are narrower than the all-surface CRM matrix. |
| T10.06 Legitimate numeric monetary values remain valid. | implemented-unverified | [P] S21-12; no condition-level all-surface evidence identified. |

## S21F:T11 - Comments And Actions

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T11.01 Add, edit and pin a comment from the deal page. | verified(local) | [T11](evidence/baseline/t11-tracking.md),43442/1441649 actual browser/API/PG create/edit/pin. |
| T11.02 Create, edit and complete an action from that page. | verified(local) | Same run: registered assignee, title/due-date edit, completion and persisted state. |
| T11.03 Reload preserves changes and latest activity is correct. | verified(local) | Same run: exact comment/pin/action/due date after reload; latest activity kind/actor/order. |
| T11.04 Another role gets appropriate access and unauthorized edits fail. | verified(local) | Same fixture actual ASGI/PG: Sales own edit permitted, other-author403 with unchanged value/audit, HR cross-author edit permitted; local auth adapter explicitly declared. |
| T11.05 Simultaneous updates do not silently overwrite each other. | verified(local) |43442 plus durable69943: actual PG wait PIDs, two independent sessions,200/409, independent literal retained values and exact+1audit/+1actionevent. |
| T11.06 CRM notes stay read-only and separately attributed. | verified(local) |43442: synthetic CRM note visible source/author/time and escaped text, no edit control; genuine PATCH409. Not live connector ingestion. |

## S21F:T12 - Personal Alerts And Lists

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T12.01 Configure per-user alert and trigger its event through the application. | implemented-unverified | [P] S21-14: scheduler/preferences exist, per-user event journey missing proof. |
| T12.02 Due-date change cancels obsolete reminder. | implemented-unverified | [P] S21-14 leaves obsolete cancellation/replay open. |
| T12.03 Completing the action cancels its reminder. | implemented-unverified | [P] S21-14. |
| T12.04 Disabled rule prevents its reminder. | implemented-unverified | [P] S21-14; verified sourcing-rule disable is a different domain and is not substituted. |
| T12.05 Replayed delivery produces no duplicate notification. | implemented-unverified | [P] S21-14/OP-02. |
| T12.06 Saved-rule group membership updates appropriately. | implemented-unverified | [CF] shared uncapped membership is tested; complete rule/event workflow remains. |
| T12.07 Manual watchlists stay stable and do not leak inaccessible records. | implemented-unverified | T39 and current-filter extension pass locally; full T12 event/rule-change stability remains unverified. |

## S21F:T13 - Calendar Oracle

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T13.01 Ten-person Oracle B matches independent monthly scheduled/billable/paid hours. | verified(local) | [O] production quantities match independently enumerated 207 billable/217 paid days, 16560/17360 hours. |
| T13.02 Oracle B monthly money and GM match independent expectations. | verified(local) | [O] USD1656000 revenue/1041600 cost, GM0.3710144927536231884057971014, monthly checks; [P] precision fixes later integrated. |
| T13.03 Partial-month and part-time quantities apply once. | verified(local) | [CM] three people at25% yield60 billable/66 paid hours, independent paid-holiday expectation; original31 later unchanged green. |
| T13.04 Mixed-location calendar cases and holiday details remain correct. | verified(local) | [Connected calendar](evidence/baseline/t13-calendar.md):41842/00371d2 exact visible and persisted US60/60/66, India80/80/88;7200/2178 and6400/3520 money; holiday days and India floor breach. |
| T13.05 Missing calendars/costs stay unresolved. | verified(local) | Same proof: separate missing-calendar/cost/short-coverage API assertions; persisted missing draft stays null/incomplete, browser correction then save/reload. No zero-cost or passing policy substitution. |
| T13.06 No mandatory manual aggregate hours are required. | verified(local) | Same real editor workflow enters daily patterns/calendar/rates only; server derives all aggregate hours. Full broader calendar registry/staging remains under S21-15. |

## S21F:T14 - Amendments

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T14.01 Extension changes rate, headcount and term. | implemented-unverified | [P] S21-16: full signed extension remains critical-path work. |
| T14.02 Original stays active while amendment is pending. | verified(local) | `test_s21_amendment_pending.py` at f75208d: change hooks never void a released/verified package, and a revision of a signed version defers supersession (amendment_draft_of) so the original schedule keeps counting until activation. Staging journey remains under T30.02. |
| T14.03 Required amendment approvals and signature complete. | implemented-unverified | [P] S21-16; original-contract release does not prove amendment flow. |
| T14.04 Activation produces the correct effective schedule and Project term. | verified(local) | `test_s21_amendment_activation.py` at aeee545: releasing an amendment supersedes the original package+version in the same transaction, the amendment Project baseline carries the amendment term, and signed outlook switches to the amendment schedule (with 5a528ac read-side filter). UI term display and staging remain under T14.01/T30.02. |
| T14.05 Renewal alerts and continuing team update correctly. | implemented-unverified | [P] two-calendar-month renewal fix8857936 is narrower than extension/team/scheduler integration. |
| T14.06 Nonrenewal is handled correctly. | verified(local) | 6955f70: explicit `outcome=not_renewing` closes the renewal, files closeout + roll-off tasks on the account owner due at term end (audited, notified), and provably leaves the released package/version untouched; sheet sends the explicit outcome (`RenewalWorkspaceSheet.test.tsx`). Staging journey remains. |
| T14.07 Overlapping periods and a late callback cannot activate stale economics. | verified(local) | b8e87c1/aeee545: verify/decline/expire refuse non-current packages, replaced uploads and superseded pinned versions; release refuses a stale pinned version; activation records explicit overlap_days/gap_days (`amendment.activated` audit). Staging breadth remains. |

## S21F:T15 - All Seven Pricing Journeys

The following conditions each apply to **all seven** original profiles: fixed
assignment, recurring MSP, staffing, T&M, milestone, unit/story point and hybrid.

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T15.01 Upload a real fixture file through the UI for every profile. | verified(staging) | `t15-seven-profile-uploads.spec.ts` on rev 76 with live Bedrock: all seven profile fixtures uploaded through the real browser UI bound to isolated fixtures, workspace rendered, extract_status=complete, suggested engagement matched per profile (tm long-form synonym accepted per the app alias table); every fixture deleted with drained jobs; zero-leak gate clean afterward. Log [t15-seven-profiles-8ca0cb3.txt](evidence/staging/t15-seven-profiles-8ca0cb3.txt). |
| T15.02 Inspect field evidence and correct extraction for every profile. | implemented-unverified | [P] editors/conflict review exist; all-profile extraction/held-out evidence remains. |
| T15.03 Save and reload every profile without losing source evidence. | implemented-unverified | [H] four connected editor cases and [P] independent40-case UI boundaries are subsets. |
| T15.04 Calculate each profile's intended economics. | verified(local) | [CM] all seven match literal totals; original31 unchanged green after fixes. This is calculator-level only. |
| T15.05 Approve each profile through required functions. | implemented-unverified | [J] one hybrid five-role path, not the seven-profile matrix. |
| T15.06 Sign each profile in sandbox with matching immutable version. | implemented-unverified | [J] one real-extracted signed hybrid, synthetic local identities. |
| T15.07 Hand off each signed profile successfully. | implemented-unverified | [J] one accepted Delivery handoff only. |

## S21F:T16 - Adversarial Extraction

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T16.01 Scanned input preserves original upload and usable evidence or explicit review. | verified(staging) | `3a75455`: bound and unbound scanned uploads share one Textract result for classification/extraction, retain the original S3 object and record OCR provenance. Staging revision73 accepted a zero-text-layer PDF, preserved it as explicit `manual_required` review with `extract_source=textract`, then cleanup/leak gate passed. Live usable OCR remains unavailable because the task role has no Textract action; the accepted explicit-review fallback is proved. [OCR staging receipt](evidence/staging/ocr-candidate-3a75455.json). |
| T16.02 Conflicting totals/dates are flagged rather than silently selected. | implemented-unverified | [P] tokenized conflict review exists; held-out conflicting originals not established. |
| T16.03 Missing year is flagged rather than fabricated. | implemented-unverified | [P] S21-04/18 missing-year quality matrix remains. |
| T16.04 Missing currency does not silently become USD. | verified(local) | [P] 0cbb530/CAD browser40089: explicit currency correction, plus confirmed/default guards; broader ambiguous originals remain. |
| T16.05 Unsupported pricing remains an explicit exception with editable evidence. | verified(local) | [H] 5c9a7fb/cf51a3ea preserves original unsupported record/evidence while replacement saves. |
| T16.06 Embedded hostile instructions cannot change reviewers or policies. | implemented-unverified | [G]/[P] schema/prompt guards exist, held-out hostile-instruction extraction evaluation remains missing. |
| T16.07 Failed extraction preserves the uploaded file and displays exceptions. | implemented-unverified | [P] failure/manual-required paths exist; all original adverse input classes not exercised together. |
| T16.08 Re-extraction keeps manual corrections until explicit review. | verified(local) | [P] 48f47f4/57f7269 replay preservation; e75af5c review and72786 real-PG confirmation-race proof. Not all live corpus cases. |

## S21F:T17 - Connected Deal Journey

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T17.01 Pipeline -> client -> named no-SOW deal -> upload binds the same identities. | verified(local) | [J] authorized local Pipeline list/detail, same client/deal and real upload; ASGI, not full browser navigation. |
| T17.02 Confirmation -> complete workspace -> signature -> handoff works continuously. | verified(local) | Fresh browser96337 PASSED1/4.8m at f74df880e8b1a718e0544accb8f9e1d32730d77c. Empty owned DB through actual Pipeline/client/deal upload, real extraction, confirmation, exact24k revenue/10k cost, five named role approvals, actual signed-byte verification, Delivery acceptance and one source-bound persisted project, with zero agreements and no page errors. No diagnostic restart. [Receipt](evidence/baseline/t17-8d7c388a-connected-browser.json). Local identity/SES adapters, real PG/S3/Bedrock; not staging. Earlier failures remain in runtime history. |
| T17.03 NDA/MSA presence has the required nonblocking semantics. | implemented-unverified | Integrated7cbdac7 plus shared UI. Browser59018 at a612b71 + dirty accessible fieldset fix passed actual NDA/MSA uploads, presence on client/deal/SOW documents/Legal register, replacement and exact v1/v2 real-S3 bytes/hashes; final DTO equality failed only on rotating signed URL. Read-only continuation61252 passed source hash/identity preservation. Evidence baseline/t17-agreement-browser.json. Zero-agreement approvals/release49137 proves bounded nonblocking behavior. Fresh uninterrupted green run and full role/Legal semantics remain. |
| T17.04 No SOW stub, delete control or readiness appears before upload. | verified(local) | Browser29816 at7f4202cccebc41c607ec4ac2e42fdc3a4e130a54 asserts zero PG SOW/version/package/project rows, same Pipeline/client/deal, visible No SOW, no Delete SOW button or Readiness region before uploading. [Assertion receipt](evidence/baseline/t17-connected-browser.json); later independent commercial-input failure does not invalidate these earlier assertions. |
| T17.05 Repeated handoff events still create exactly one project. | verified(local) | Browser49137 on6ad2171: actual signed verification, Delivery acceptance, owner release, exact one project pinned to approved SOW/GM/package; repeat POST409 and identical persisted project/baseline/tasks/upload counts. [Receipt](evidence/baseline/t17-repaired-handoff.json), tests/e2e/local/s21-t17-signature-resume.spec.ts. Diagnostic continuation, not uninterrupted T17.02 or staging. |
| T17.06 Gates and names are clear and open-deal counts reconcile. | verified(local) | Browser71535 at a612b71 passed actual API/PG/UI open counts, client/deal/workspace names and exact source version. Readiness state tests28000 passed19, loader integration93052 passed21, and browser94587 at60457f3 plus the committed owner-render patch passed actual current-package Delivery acceptance/release gates, responsible owner and permitted View handoff action. Evidence baseline/t17-route-audit.json and t17-readiness-routes.json. Not staging. |
| T17.07 Existing test-data leak gate passes in this journey. | verified(staging) | [J-STG] journey teardown drained to done and the same-revision deploy smoke leak gate reported 0 test clients / 0 e2e approvers on real SOWs. |
| T17.08 Route inventory passes on this revision. | implemented-unverified | Browser71535 at a612b71 passed all eight released-workspace tabs/reloads/back navigation and normal-reader denial on Pipeline/client/deal/SOW routes, with no page errors. Evidence baseline/t17-route-audit.json. Broader role/state route inventory remains, so not yet closed. |

## S21F:T18 - Five Forecast Views

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T18.01 All five Forecast views open with persisted data. | verified(local) | [T18 evidence](evidence/baseline/t18-five-views.md):25161 passes real persisted five-view navigation;99259 verifies populated Overview January source/value. Controls are separately evidenced in .06. |
| T18.02 Filter and drill company -> account -> source -> monthly detail. | verified(local) | [P] FC-02/03/04 and [H] real three-view scope/reload/CSV browsera1354ea, drilldown/15 months e8eeb9e. |
| T18.03 Scope, period and scenario survive navigation. | verified(local) | [T18 evidence](evidence/baseline/t18-five-views.md):25161 real company/account/source drill, allfive tabs, resource link, Back, selected-month CSV and horizon invalidation pass.26 focused regressions41393. |
| T18.04 Current quarter stays separate from future totals. | verified(local) | [F] pure Company X expectations/horizon rollover; [H] future196000->140000 browser assertions. |
| T18.05 Names plus empty/error states are honest in every view. | verified(local) | [T18 evidence](evidence/baseline/t18-five-views.md):67649 empty/error case passes allfive views with real account names and explicit recovery;25161 populated named account/source passes;99259 resource-specific Reload recovery passes. |
| T18.06 Every visible control performs its intended action. | verified(local) | [T18 evidence](evidence/baseline/t18-five-views.md):25161 navigation/export,99259 persisted assumptions/publication and recovery,31702 mapping/history controls,32834 source paging/deal links/disclosure,69292 exact nonempty clear/restore prefix,8316 source anchor/Back after ad30e77 repair.34 affected UI tests79245/typecheck77526. Honest unavailable renewal/linkage notices remain parent FC-01 gaps; no staging claim. |

## S21F:T19 - Financial Oracles

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T19.01 Company X signed, Expected and Upside match independent monthly/quarterly literals. | verified(local) | [F] current24000/122000/164000 and future0/196000/280000; [J] independent signed24000/cost10000 source separately passes. |
| T19.02 Company X account sums reconcile to company totals. | verified(local) | [F] exact scenario/horizon calculation and [H] connected future196000/98000 then140000/70000; bounded fixture only. |
| T19.03 Accepted six-account preview matches all monthly/quarterly/scenario totals. | verified(local) | [Persisted matrix](lanes/t19-preview-verification.md):25684 real API twelve sources, six accounts, fifteen months, five quarters, three scenarios; exact monthly revenue/cost/source IDs and versions. API app4c80296; fixture14136/worker78528. [Artifact](evidence/baseline/t19-preview-matrix.json). No staging claim. |
| T19.04 Date, value and probability edits survive reload. | verified(local) | Browser54224/app44fec51 changes dates/allocations/cost month explicitly, fee30000->36000, probability.35->.5 via visible controls; three separate worker runs, reload and immutable PG history versions1-4. [Proof](lanes/t19-plan-terms.md). |
| T19.05 Every affected view reconciles after each edit. | verified(local) | Browser54224 checks account/company, Overview, Revenue, Next opportunities after each change; no staffing change in this source. Independent QA required old-period/cost strengthening:93529 passes December228200/Q4690200, no ghost source, final company174000/684400/930400 across scenarios, latest source revenue/cost0/0,18000/9000,36000/18000. [Final artifact](evidence/baseline/t19-preview-old-period.json). All five clauses supported locally, no parent/staging closure. |

## S21F:T20 - Conversion And Deduplication

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T20.01 Link forecast to real CRM deal and convert to one signed SOW. | implemented-unverified | [P] FC-05/08: conversion storage/guards exist, complete CRM promotion/signed journey remains. |
| T20.02 Repeated sync replaces potential with contract exactly once. | implemented-unverified | [P] FC-05 repeated sync journey remains. |
| T20.03 Partial conversion leaves exactly the uncovered economic scope. | implemented-unverified | [F] independent arithmetic exposed residual defect; [P] dd4ac6d/ee4659c fixes/guards are bounded, full persisted conversion journey open. |
| T20.04 Two SOWs under one deal are not double counted. | implemented-unverified | [P] FC-05 explicitly remaining. |
| T20.05 Lost deals do not contribute potential. | verified(local) | [F] independent pure lost/unselected exclusions pass; not the full CRM lifecycle. |
| T20.06 Duplicate source input cannot double count economics. | implemented-unverified | [F]/[P] repaired economic-identity checks exist; repeat-sync/source lifecycle breadth remains. |
| T20.07 Alternative options do not count simultaneously. | verified(local) | [F] pure unselected alternatives excluded, conflicting selected sources rejected. |
| T20.08 Effective amendments do not double count original contract. | verified(local) | `test_s21_amendment_no_double_count.py` at 5a528ac: signed outlook excludes superseded versions/packages; after activation only the amendment schedule counts (400→600, never 1000). Staging reconciliation remains under T20/T30. |

## S21F:T21 - Actuals And Financial Edges

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T21.01 Zero/unknown revenue and incomplete cost remain explicitly unassessed. | verified(local) | [CM] zero/missing-cost cases and [F] signed known revenue with unknown cost versus unsigned exclusion; [P] consumer fixes integrated. |
| T21.02 Mixed currencies require explicit FX/evidence. | verified(local) | [CM] EUR/USD literal1025 revenue/190 cost; missing FX unresolved; [F] explicit FX provenance. |
| T21.03 Fixed-fee allocation conserves agreed minor units. | verified(local) | [CM] USD100.01 at2:1 becomes66.67/33.34 independent of input order. |
| T21.04 Milestone economics and rounding conservation are correct. | verified(local) | [CM] all seven literal calculator profiles and confirmed-minor-unit conservation pass; [J] broader connected milestone/currency journeys remain separate. |
| T21.05 Duplicate actual import creates no extra revision. | verified(local) | [J] same signed-project financial import replay passes. |
| T21.06 Correction retains immutable history and unrelated financial bases. | verified(local) | [J] recognized12000.01 ->11000.99; billed15000/cash8000/cost6000 unchanged, source GM/baseline/schedule retained. |
| T21.07 Combine only matched actual-to-date with uncovered forecast. | verified(local) |19ca6f7: full financial browser76926 exact23000.99/11000, corrected22500/11000, unchanged signed schedule; PG overlap201/422, JSON-null migration and history guard; identity11028 and concurrent replay/responsive33980 pass. [Proof/boundaries/history](evidence/baseline/t21-coverage.md). |
| T21.08 Billed amounts never silently become recognized revenue. | verified(local) | [J] exact four separate bases remain distinct through correction. |

## S21F:T22 - Full-Team Demand

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T22.01 Company X at70% retains2 US/onshore +5 India/offshore people. | verified(local) | [D] literal service oracle; [S5] 11:29 connected source/browser seven-head proof. |
| T22.02 Scenario/probability changes leave headcount seven. | verified(local) | [D]70%->20/100/0/unknown service cases; [S5]70%->40% and Upside browser preserves seven. |
| T22.03 Overlapping opportunities compete globally without double matching one person. | verified(local) | [D] earlier competing account consumes US/India people before account/Sales filters; Company X has zero US/three India matches and four-FTE gap. |
| T22.04 Part-time capacity is matched correctly. | verified(local) | Browser84625/e879213: real half-time source/import/sourcing,7people/3.5required/2.5matched/1gap, exact identities at70/40%; [proof](evidence/baseline/t22-part-time.md). |
| T22.05 Roll-off releases capacity on the correct date. | verified(local) | [D] foreign commitments inclusive through15Nov, available16Nov; peak November gap seven. |
| T22.06 Continuing teams retain continuity rather than appearing as new hires. | verified(local) | [D] seven retained people reuse own commitments; eighth slot adds only one incremental gap. Scope is same-plan service continuity, not every signed amendment. |
| T22.07 Sourcing dates reflect actual regional rules/intervals. | verified(local) | [S5] Sept17/Oct2 every continuous-gap interval; [J] released seven-head draft September1 under its separate explicit fixture. |

## S21F:T23 - People Publication And Sourcing

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T23.01 Publish forecast demand into actual People view. | verified(local) | [S5] persisted hybrid/browser publication and sourcing views; [J] retained released-project event separately. |
| T23.02 Prepare a sourcing draft and retain its history. | verified(local) | [S5] drafts[2,1] reload/current history; [J] review -> complete seven-head draft with old jobs/drafts unchanged. |
| T23.03 Start/headcount changes update published demand and sourcing. | verified(local) |88901/23dffd9 API-authored date/headcount change, visible stale->republish->draft,8heads/4FTE/1.5gap and immutable old lines/history; [proof](evidence/baseline/t23-publication.md). |
| T23.04 Replayed events create no duplicate sourcing request. | verified(local) | [J] separate workers2/1/0 and replay0 do not duplicate current draft; bounded release/supply/enrichment events. |
| T23.05 Restricted readers cannot see costs. | verified(local) |49160/23dffd9 Sales-only actual populated data/UI, canonical nonzero financial sentinels excluded, protectedreads403;44 regression74987. [Proof](evidence/baseline/t23-publication.md). |
| T23.06 Planning endpoints cannot reserve or hire people. | verified(local) |88901 valid publication/draft+forbidden actionextras422, unchanged audit/version/workforce; success also leaves workforce unchanged. [Proof](evidence/baseline/t23-publication.md). |

## S21F:T24 - Evidence Automation

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T24.01 Fixture SOW/findings traverse extraction, plan preparation and exception review. | implemented-unverified | [J] extraction/governance/sourcing connected; [P] broader exception/plan preparation remains, not one whole auto-plan journey. |
| T24.02 Source change automatically refreshes derived state. | verified(local) | [J] release/supply/enrichment produces review then complete seven-head draft via separate workers. Other event domains remain separate. |
| T24.03 Worker honors a disabled rule. | verified(local) | [P] browser9704 and private-PG crash21501 record disable/recovery behavior; [J] same-source disable is not claimed. |
| T24.04 Re-upload/retry/re-extract do not duplicate plans. | verified(local) | [P] `test_s21_plan_singularity.py`: connected upload→plan journey holds exactly one ForecastPlan/version/job across same-byte re-upload, failed-job retry upload, mutable-version re-extract and same-key plan replay; changed inputs under the same key 409 without a second plan; real-PG concurrent same-key race (disposable `s21_t24_plan_race`) serialized to one plan. Staging journey breadth remains under T24.01. |
| T24.05 Re-extraction does not lose human overrides. | verified(local) | [P]48f47f4/57f7269 plus conflict review/confirmation race proof; live held-out breadth remains. |
| T24.06 Evaluate a separate held-out live-model sample. | missing | [P]/[G] explicitly missing corpus/quality evaluation; one live successful SOW is not held-out assessment. |

## S21F:T25 - Exports And Snapshots

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T25.01 Export every authorized row. | implemented-unverified | [P] FC-11 all-row breadth pending; selected-account CSV browser evidence is narrower. |
| T25.02 Screen/API/export reconcile at the same immutable snapshot. | implemented-unverified | [P] FC-11; mutable Pipeline multi-page export QA existed at cutoff, not proof of Forecast snapshot parity. |
| T25.03 Historical Forecast snapshots remain inspectable and correct. | implemented-unverified | [P] immutable schedule/history exists; [J] financial revision history is not historical Forecast export. |
| T25.04 Stale events cannot overwrite newer results. | implemented-unverified | [P] FC-12 persistent jobs/stale guards, complete event graph remaining. |
| T25.05 Concurrent edits preserve expected revision authority. | implemented-unverified | [P] actual-PG CAS proofs are scoped; complete Forecast/export concurrency condition not established. |
| T25.06 Tenant/role boundaries hold for rows, aggregates, deep links and CSV fields. | implemented-unverified | [P] FC-11/12 explicitly leaves full permission/export/deep-link matrix. |

## S21F:T26 - Accessibility And Responsive Behavior

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T26.01 Keyboard navigation reaches the actual screens and controls. | implemented-unverified | [P] T26 cross-application accessibility remains despite responsive captures. |
| T26.02 Forms have labels and dialogs return focus correctly. | implemented-unverified | [P] T26; no complete audited label/focus matrix identified. |
| T26.03 Validation errors are actionable. | implemented-unverified | [P] individual editors tested; cross-application errors remain. |
| T26.04 Browser Back preserves intended navigation. | implemented-unverified | [P] DG-03/S21-11/T26 full workflow remains. |
| T26.05 Loading, error and retry states work. | implemented-unverified | [P] FC-01/T26; all screen-state combinations not established. |
| T26.06 Long names and zero-data states fit and remain honest. | implemented-unverified | [P] T26; overflow fix is a narrower signatory-grid case. |
| T26.07 Desktop/mobile tables scroll inside their container without page overflow. | implemented-unverified | [S5] sourcing/resource screens and [P]19949 signatory flows pass locally; entire application surface remains unverified. |
| T26.08 Controls outside table cells also remain usable. | implemented-unverified | [P] T26 full navigation/screen requirement, not covered by table-only screenshots. |

## S21F:T27 - Source Failures

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T27.01 CRM429 and timeout retry/reconcile without data loss. | implemented-unverified | [P] CO-07/T27 broader failure/recovery matrix remains. |
| T27.02 Expired access is explicit, not healthy/fresh status. | implemented-unverified | [P] S21-10/CO-07; no fresh live credential-failure proof identified. |
| T27.03 Duplicate and out-of-order webhooks do not duplicate or regress records. | implemented-unverified | [G] actual intake replay controls and [SC] archive-version controls are bounded; full webhook matrix remains. |
| T27.04 Failure does not falsely advance freshness. | verified(local) | [SC] pre-lease metadata and partial archived-owner failure remediation,82 combined passes; no live CRM/staging claim. |

## S21F:T28 - Recovery

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T28.01 Worker restart between commit/event handling yields one business result. | verified(local) | [P]/[H] privatePG separate-worker mid-INSERT kill/recovery, exact2publications/2drafts/audit valid; bounded sourcing domain. |
| T28.02 Duplicate upload is singular. | verified(local) | Sequential same-byte upload returns the original job; a failed-job retry reuses it and leaves exactly one upload job, opportunity, SOW and version. Identical revision bytes return409. Focused3 passed at the integration checkpoint after `baa8de7`; concurrent/provider retry breadth remains under T24.04/FC-09 rather than reopening this literal condition. |
| T28.03 Duplicate submit and handoff are singular. | implemented-unverified | [G] release-link idempotency and [P] confirmation locks are subsets, not complete duplicate lifecycle matrix. |
| T28.04 Storage failure exposes a recoverable retry state. | implemented-unverified | [P] deletion retry/status exists; all required storage failure schedules not identified. |
| T28.05 Stale callback cannot resurrect deleted or superseded source. | implemented-unverified | [P] S21-01/FC-12 complete late-callback/event graph remains. |

## S21F:T29 - Migration And Restore

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T29.01 Migrate a representative populated database. | implemented-unverified | [H] source-facts legacy-row upgrade and retained local DB upgrades exist; representative legacy model/population matrix not established. |
| T29.02 Interrupt backfill and resume safely. | verified(local) | [P] CO-07 realPG lock/rollback/same-generation resume and [SC] fixed checkpoint/lease cases; not deployed process recovery. |
| T29.03 Verify foreign keys and exact row counts. | implemented-unverified | [PC] SQLiteFK and [H] migratedPG proofs cover selected graphs, not representative migration counts. |
| T29.04 Preserve all legacy models, agreements and actuals. | implemented-unverified | [P] S21-18/CO-07 and [G] legacy ActualPeriod reconciliation remain. |
| T29.05 Test rollback and restore with malformed/concurrent migration data. | verified(local) | `scripts/s21_migration_restore_proof.py`, receipt [t29-restore-proof.json](evidence/baseline/t29-restore-proof.json): populated head→0061→head rollback fingerprint-stable over 10 seeded tables; populated downgrade loss-refusal; real pg_dump -Fc/pg_restore equality incl. alembic head; malformed deletion_job data fails 0053 atomically (version unchanged, no partial DDL); two concurrent process upgrades → one clean winner, single head row. Staging-process recovery remains under T29.02/OP rows. |

## S21F:T30 - Combined Staging Journey

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T30.01 Complete Company X journey on one combined staging revision. | verified(staging) | [J-STG] connected-journey-8ca0cb3.json: full chain on staging rev 76 (API+workers+SPA image s21-8ca0cb3), fixture → Pipeline/Deal → real S3+Bedrock upload → 17 confirmations → commercial 24000/10000 → five distinct real-policy approvals → signed verify → Delivery acceptance → release → one Project → Forecast account/company outlook incl. quarters → People project-demand publication → amendment draft deferring supersession without double count → pinned comment/action/navigation → durable three-level deletion done. Owner click-through remains the acceptance gate. |
| T30.02 Complete a staffing extension on that revision. | implemented-unverified | Candidate deployed (rev 76); amendment-draft deferral proven on staging in [J-STG]; the completed signed-extension journey (approvals→signature→activation on staging) remains. Activation itself verified(local) at aeee545. |
| T30.03 Complete deletion on that revision. | verified(staging) | [J-STG] client deletion job drained to done through the three-level durable graph on rev 76; deploy-smoke zero-leak gate clean on the same revision. |
| T30.04 Verify every integration/resource update/aggregate reconciliation together. | implemented-unverified | [J-STG] covers forecast account/company/quarters and People demand on rev 76; HubSpot 657-deal reconciliation proven same-day on the same environment. Full cross-integration simultaneous sweep and PO workflow remain. |

## S21F:T31 - Representative Load

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T31.01 Measure list/filter/summary/export at10000deals/1000SOWs/24buckets or declared larger actual scale. | verified(local) | `scripts/s21_load_proof.py`, receipt [t31-load-proof.json](evidence/baseline/t31-load-proof.json): 10000 deals/200 clients/1000 SOWs/24 close-date buckets/9 stages on owned PG16; 30 requests per surface through the deployed query paths. Staging-host measurement remains. |
| T31.02 Pagination remains correct under that load. | verified(local) | Same receipt: pages 1/2/50/99/100 at page_size=100 over the 10k population are pairwise disjoint, 100 rows each, total_reported=10000. Full-walk and staging remain. |
| T31.03 No per-row external API calls and query counts remain bounded. | verified(local) | Same receipt: per-request SQL statement counts constant at the 10k load (list/filter 8, summary 4, whole-export 35) across 30 requests each — no per-row amplification; earlier cad16d0 source-count proof retained. |
| T31.04 Record hardware/concurrency and p95 list<=2s/summary<=3s, reporting misses honestly. | verified(local) | Same receipt records hardware (4-cpu x86 macOS, dockerized PG16, in-process ASGI, sequential single client): list p95 1078ms <= 2s, filter p95 302ms, summary p95 98ms <= 3s. HONEST MISS recorded: whole-pipeline CSV export p95 92.9s at 10k rows (no stated gate; listed as an open nonblocking defect, offset-paged 1000-row assembly). |

## S21F:T32 - Authorization

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T32.01 Unauthorized direct API edits are refused and audited correctly. | implemented-unverified | [P] scoped APIs/QA/PG guards exist; cross-feature mutation/audit matrix not established. |
| T32.02 Cross-account/tenant reads are refused. | implemented-unverified | [P] financial/planning/project grants tested in subsets; [CF] ordinary CRM rows lack tenant fields, so no invented whole-app isolation. |
| T32.03 Restricted roles cannot obtain cost fields. | implemented-unverified | [P] cost redaction/People projections exist; every direct endpoint/field combination still pending. |
| T32.04 Forged test tags confer no authority. | implemented-unverified | [P] issued provenance controls exist; full direct attack/audit scenario remains. |
| T32.05 Reviewer bypass is refused server-side. | verified(local) | [P]/[O] repaired CEO/task/dispatch containment plus explicit reviewer guards; local bounded paths only. |
| T32.06 Refusal never leaks through aggregate counts or exports. | implemented-unverified | [CF]/[J] exact scoped Pipeline controls pass; all financial/report exports and roles remain [P] FC-11/12. |

## S21F:T33 - Infrastructure And Monitoring

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T33.01 Fresh whole-root Terraform plan identifies correct account/region/state and exact resource diff. | blocked | [P] OP-01/CO-06: existing plan is not approval-ready; refreshed exact-image reviewed plan needed. |
| T33.02 Human approval matches the actual applied change. | blocked | [P] infrastructure approval/apply not executed. |
| T33.03 Isolated sync stall triggers the intended alarm and destination. | blocked | [P] deployed alarm/stall/delivery proof pending approved infrastructure. |
| T33.04 Recovery clears the incident. | blocked | [P] OP-01 deployed recovery proof absent. |
| T33.05 Heartbeat/missing-data logic detects actual stall but not quiet CRM. | implemented-unverified | [G] quiet/poison consumer local tests are meaningful; deployed alarm behavior remains blocked, not proved by task existence. |

## S21F:T34 - Six-Person Mail Readiness

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T34.01 Every exact roster address is verified by domain or identity in sending region. | blocked | [P] OP-02 missing regional coverage; alias/domain assumptions insufficient. |
| T34.02 Distinguish created, verified, eligible, queued, accepted and delivered states. | implemented-unverified | [P] documented states/readiness path exist; six-person end-to-end status proof blocked. |
| T34.03 Routine deployment sends no duplicate verification requests. | implemented-unverified | [P] OP-02 approved setup/deploy proof remains, not inferred from Terraform declarations. |
| T34.04 Authorized delivery check reaches intended inbox. | blocked | [P] OP-02/05 identities/recipient verification and provider approval; SES sink is not delivery. |

## S21F:T35 - Liberty Recovery

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T35.01 Inspect the precise contaminated cycle, preserving SOW/version/history. | implemented-unverified | [P] OP-03 exact cycle observed voided/no active assignments; full history/outbox audit still needed, no repeat cancellation. |
| T35.02 Repair rejects old tasks and callbacks. | implemented-unverified | [P] OP-03 fixture failure/destructive paths and downstream audit remain. |
| T35.03 Preview real eligible reviewers. | implemented-unverified | [P] OP-03/S21-06; exact roster readiness dependency. |
| T35.04 Intentionally resubmit once, with exactly one new cycle and correct tasks/notifications. | blocked | [P] OP-03 PO-directed resubmission after real roster/mail readiness; not authorized by this report. |
| T35.05 Exercise destructive/failure behavior on isolated fixture before live remediation. | implemented-unverified | [P] OP-03 explicitly pending; local containment unit tests are not the complete repair rehearsal. |

## S21F:T36 - Human CRM Canary

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T36.01 Human saves named HubSpot canary, not a synthetic local fixture. | blocked | [P] OP-04 not started; human source action required. |
| T36.02 Normal sync exposes complete record within120seconds, without manual-sync shortcut. | blocked | [P] OP-04/CO-06 deployment/consumer/human prerequisites. |
| T36.03 Update propagation, filters/counts and no-SOW-stub behavior are correct. | blocked | [P] OP-04; local fixture projection is explicitly not this source proof. |
| T36.04 Record t0/t1, source fields, exact revisions and cleanup/reconciliation. | blocked | [P] canary protocol prepared only; no execution artifact. |

## S21F:T37 - SES Production Access

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T37.01 Prepare truthful request and submit through approved workflow. | blocked | [P] OP-05 draft exists, authorized account-operator submission not performed. |
| T37.02 Record actual AWS outcome and quotas without false green on pending/denied. | blocked | [P] OP-05 AWS decision external/unbounded; no production approval claimed. |
| T37.03 Verify sender configuration and bounce/complaint handling. | implemented-unverified | [P] OP-05 controls still need verification; draft wording is not operational proof. |
| T37.04 Controlled delivery works after approval. | blocked | [P] OP-05 actual approval/identity/inbox dependency. |

## S21F:T38 - Release Baseline And Legacy Reconciliation

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T38.01 Resolve actual full main SHA and release tag. | verified(local) | [P] CO-01 records main/tag321b365 verification; baseline identity only, not new S21 release. |
| T38.02 Actual image/digest and stable service match released baseline. | blocked | [P] CO-01 observes older s20-27e2edec image; exact release binding unresolved. |
| T38.03 Check-only smoke succeeds for that same baseline. | blocked | [P] CO-01 records extraction failure; later local provider proof is not deployed smoke. |
| T38.04 Reconcile every legacy row including T32/T34/FINAL-T38. | implemented-unverified | [P] CO-02/G:65legacy rows and150xfails inventoried, replacement/full-scope evidence still incomplete. |
| T38.05 Account for local/staging selection, all executed/skipped/xfail/not-run counts. | implemented-unverified | [P] exact frozen local counts exist; final combined/staging selection outstanding. |
| T38.06 No unsupported all-green claim or skipped failure substitutes for proof. | verified(local) | [P]/[G] explicit150inheritedxfails+1live skip and legacy11browser skips preserved; no full scenario promoted. This is evidence-accounting discipline, not application acceptance. |

## S21F:T39 - Watching (Passed Locally)

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T39.01 Empty Watching card shows 0. | verified(local) | Browser46207 at941953a: card0, destination0 and exact empty API set; T39 evidence above. |
| T39.02 One watched deal in three groups yields exactly one matching row and total. | verified(local) | Same run: three exact group memberships, watch and combined-group API total1/exact identity. |
| T39.03 Card and destination list reconcile exact identity, not just count. | verified(local) | Same run: card1 opens exactly one visible row with the authorized watched deal ID. |
| T39.04 Unwatch returns card/list to 0. | verified(local) | Same run: real unstar persists, card0, API empty/count0, destination0/no rows. |
| T39.05 Access filtering excludes inaccessible identities from both surfaces. | verified(local) | Same run: other actor's watch/detail denied404, exact API/UI population excludes its ID; affected54pass. |

## S21F:T40 - Approval Card

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T40.01 Mixed reviews yield distinct in-review SOW-package count. | verified(local) | Browser99369/205d51a: zero and mixed two-review/approved/draft/restricted fixture; T40 evidence above. |
| T40.02 Card and approvals destination contain exactly the same identities. | verified(local) | Same run: card2, exact two IDs, pinned population revision, reload and stale409/explicit refresh. |
| T40.03 Multiple reviewers do not multiply one SOW. | verified(local) | Same run: five distinct assignments per package, ten assignments count as two packages. |
| T40.04 Two SOWs under one deal remain two. | verified(local) | Same run: exact two package IDs share one deal; both cards and API pagination retain total2. |

## S21F:T41 - Formerly Skipped Full Journey

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T41.01 Execute formerly skipped legacy browser journey without its skips. | missing | [G]11skipped legacy browser steps; [J] is separate ASGI journey, not execution/retirement of that spec. |
| T41.02 Matching signed upload -> release -> Delivery acceptance produces one project. | verified(local) | [J] real signed bytes re-extracted/verified, accepted Delivery handoff and exact project ID. |
| T41.03 Known monthly actuals/GM belong to that same project. | verified(local) | [J] signed24000/cost10000 plus same-project four financial bases/correction, original GM and baseline unchanged; not complete legacy ActualPeriod reconciliation. |
| T41.04 Reject wrong versions and signatories. | implemented-unverified | [G] real service mismatch tests; [J] passing matched bytes are not the full adverse journey. |
| T41.05 Retries keep one release/project/result. | implemented-unverified | [G] service replay controls and [J] sourcing/import replay differ from full handoff retry matrix. |
| T41.06 Teardown leaves no test-data leaks. | implemented-unverified | [J] two exact S3 deletion receipts pass, retained local DB rows intentionally remain; not full leak-gate cleanup. |

## S21F:T42 - Deployed Consumer

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T42.01 Drift adoption is reviewed and apply approved. | blocked | [P] OP-01/CO-06 six old workers/absent service; prepared plan is not approval-ready. |
| T42.02 Real consumer processes with measured lag. | blocked | [P] CO-06 actual deployment/normal processing remains; running task alone insufficient. |
| T42.03 Stalled, quiet and recovery states produce correct alarm delivery. | blocked | [P] OP-01/CO-06 deployed alarms and destination proof absent. |
| T42.04 Link normal-sync human canary T36 to the same deployed consumer. | blocked | [P] OP-04/CO-06 human save and approved deployment required. |

## S21F:T43 - Backfill Chaos

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T43.01 Stage rename and source reassociation update labels and membership. | implemented-unverified | [P] source adapters exist; connected rename/reassociation breadth remains. |
| T43.02 Interrupt at checkpoint and commit boundaries, then resume same generation. | verified(local) | [P] CO-07 actualPG lock/rollback/resume; [SC] fixed persisted checkpoints/lease/cursor boundaries. Not separate deployed process proof. |
| T43.03 Resume produces complete exact-once effects. | implemented-unverified | [SC] bounded page/lease controls pass; [P] complete separate-process/deployed recovery remains. |
| T43.04 Missing/partial provider evidence cannot falsely delete records. | verified(local) | [SC] explicit false/404/malformed/wrong-ID archive controls, metadata/owner failure and finalization mapping fixes;82 combined passes. |
| T43.05 Duplicate/out-of-order source processing is safe. | implemented-unverified | [SC] strict-newer archive restoration and [G] intake replay are subsets; [P] full source event breadth remains. |

## S21F:T44 - Business Unit Truth

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T44.01 Configured, absent, empty and inaccessible metadata have distinct correct states. | implemented-unverified | [P] CO-08/S21-12 adapters+11PG oracles, full settings/permission-aware live display matrix remains. |
| T44.02 Display/filter behavior survives reload. | implemented-unverified | [P] CO-08 active facets exist, full real source/reload workflow pending. |
| T44.03 Mapped source values drive account/company grouping. | implemented-unverified | [P]494ae2e11PG membership oracles and active facet changes; complete grouping scenario not separately established. |
| T44.04 Current live availability is recorded separately from synthetic coverage. | blocked | [CF] historical property absence explicitly not fresh verification; [P] human source/canary parity dependency remains. |

## S21F:T45 - Trusted Cleanup

| Condition | Tag | Evidence or remaining boundary |
| --- | --- | --- |
| T45.01 Only aged server-issued eligible fixtures enter cleanup. | verified(local) | [PC] expired/exact-run controls plus [P]/[H]8106641 fixes unchanged QA,46affected passes. Tags/names alone confer no trust. |
| T45.02 Young active fixture survives, including explicit zero-age mode. | verified(local) | [PC] active-run protection even with exact zero age, unchanged QA remediation recorded [P]. |
| T45.03 Untagged local clients, mirrored clients and real-name collisions survive. | implemented-unverified | [PC] mirrored refusal/provenance checks pass after8106641; exact full untagged/name-collision matrix not separately recorded. |
| T45.04 Zero-age mode remains scoped to exact authorized run/owner. | verified(local) | [PC] exact-run selection, invalid-age/provenance/refusal controls; no global sweep authority. |
| T45.05 Failures/retries preserve unrelated records. | verified(local) | [PC] transaction rollback, original pending-job replay/shared-key controls; [H] prefix neighbor preserved, bounded local graph. |
| T45.06 Cleanup preserves retained financial history. | verified(local) | [PC]36924.125 plus legacy facts/frozen baseline; [H] actual worker/S3 proof retains24680.125/project. |

## Evidence Register And Limits

- [P] [Progress ledger](progress-20261002.md): current51-row/45-scenario ledger,
  timestamp18:55UTC, exact revision/run attributions and remaining scope. All
  whole requirements/scenarios remain unclosed at this cutoff.
- [J] [Connected journey](evidence/baseline/connected-20261002-d.md): revision
  d25e136/session94568, real ASGI/PG0061/Bedrock/S3/separate workers; local
  synthetic identity and SES sink, no browser/CRM/Cognito/mail/staging claim.
- [H] [Handoff](handoff.md): timestamped local checkpoints, especially Latest
  Evidence for1925e81f deletion,5c9a7fb editor and a1354ea Forecast observations.
  Later [P]/[J] supersede earlier failed or unfinished checkpoint statements.
- [O] [Independent first increment](qa/first-increment.md): literal calendar
  OracleB and exact security repros; use [P] bd22cb7 for security remediation.
- [CM] [Commercial QA](lanes/qa-commercial.md): original31 exact economics
  assertions, independent expected amounts and unchanged green reverification;
  later consumer/precision fixes are attributed by [P], not assumed from old reds.
- [F] [Forecast QA](lanes/qa-forecast.md): explicit independently expected
  scenario/horizon/FX/unknown-cost checks; [P] records subsequent persistence
  and fixes, not wholesale equivalence with the original pure run.
- [D] [Company X demand QA](lanes/qa-company-demand.md):8new+3existing cases,
  11passed at7f98459/privateSQLite actual services, no mocked feature outputs;
  exact probability/competition/continuity/roll-off conditions and limits.
- [S5] [Session05](session-05.md):11:29UTC connected sourcing browser result,
  literal7heads,70%->40%/Upside, regional dates/history and reviewed layouts.
- [CF] [CRM filters](lanes/crm-filters.md): exact SQL/HTTP population assertions,
  delayed-response/remove-chip UI boundaries, unchanged18QA+16owned remediations;
  mocks and absent full browser/export/load coverage explicitly disclosed.
- [SC] [Scan QA and remediation](qa-scan.md):21independent cases and corrected
 82combined pass record; synthetic external transport only, limitations retained.
- [PC] [Parent cleanup QA](qa-parent-cleanup.md): original faults and explicit
  passing controls/retained literals; [P]/[H]8106641 remediates eight unchanged
  failures and adds actual parent/worker/S3 proof, not all possible races.
- [G] [Regression gaps](qa-regression-gaps.md): bounded body-level distinctions
  between genuine tests and150xfail skeleton/absent-helper cases plus11legacy
  skipped browser steps. Its old defects/gaps are superseded only where newer
  evidence explicitly does so, not merely because a newer suite passes.

This condition map is not the separately owned51-requirement map. It does not
retire150inheritedxfails, the opt-in live skip or the legacy skipped browser
journey. It does not count red OCR authoring as implementation. T39 additions,
new export fixes and any later acceptance evidence require an attributable
update after this frozen inventory; they are not guessed here.

[P]: progress-20261002.md
[J]: evidence/baseline/connected-20261002-d.md
[H]: handoff.md
[O]: qa/first-increment.md
[CM]: lanes/qa-commercial.md
[F]: lanes/qa-forecast.md
[D]: lanes/qa-company-demand.md
[S5]: session-05.md
[CF]: lanes/crm-filters.md
[SC]: qa-scan.md
[PC]: qa-parent-cleanup.md
[G]: qa-regression-gaps.md
