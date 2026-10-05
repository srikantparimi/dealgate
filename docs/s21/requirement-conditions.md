# S21 And Forecast: Requirement Conditions

Evidence reconciliation dated 2026-10-02. This is a condition-level companion to
the [51-row integration ledger](progress-20261002.md), not a replacement contract,
new acceptance criteria, completion percentage, or a claim that an entire parent
requirement passed. All 51 original IDs are retained below. Related clauses are
grouped for readability; each bullet has its own state. Clause grouping is not a
weighting system. The separate acceptance matrix owns the 45 scenario verdicts.

## Reading The States

- **verified (local)**: the cited evidence demonstrates the explicitly bounded
  condition in a local environment. Unit/service/browser/provider boundaries are
  stated where material. This does not establish staging or adjacent conditions.
- **implemented-unverified**: relevant implementation exists, but the complete
  condition lacks attributable outcome evidence. Some clauses still need an
  implementation audit or completion; this is not an assertion that all code is
  finished. Missing tests alone do not mean missing implementation.
- **missing**: a concrete required capability is identified as unfinished in the
  current ledger, rather than inferred absent from a test gap.
- **blocked**: an external approval, access, named human action or provider outcome
  prevents this condition. Ordinary unfinished engineering is not a blocker.

No condition here is verified on the combined S21 staging release: no S21
candidate has been deployed. Local passes still require the contract's final
combined revision, staging parity, safe cleanup and applicable human acceptance.
Older evidence remains bounded to its recorded revision, not automatically
revalidated by later merges. The 18:55 UTC ledger is the reporting baseline;
the subsequent Pipeline CSV proof is an explicitly attributed addition. The
lead's T39 pass at941953a is recorded below with its local-only boundary.

Inventory of the grouped bullets below: **45 verified locally, 88 implemented-
unverified, four missing and 21 blocked** (158 groups under 51 requirements).
These counts describe this document's explicit groupings, not weighted progress
or unique test assertions; shared evidence and clauses can appear under multiple
original IDs. Staging-verified groups: zero.

## Evidence Key

- **V3**: [authoritative imported contract](../directives/s21-forecast-implementation.md).
  Its detailed clauses and independent numerical oracles remain normative.
- **L**: [integration ledger, 2026-10-02 18:55 UTC](progress-20261002.md).
  Commit references below identify the bounded implementation/evidence recorded
  there; they do not mean an entire row passed.
- **J**: [connected local journey](evidence/baseline/connected-20261002-d.md),
  tested `d25e1363657c22b2ec1e2cbf09cd93d5eddfaef7`, application `a6c9e7c`.
  Real PostgreSQL0061, S3, Bedrock and separate workers; synthetic local identity
  adapter and SES sink. Not live HubSpot, Cognito, inbox, staging or browser proof.
- **P**: [Pipeline projection and export evidence](lanes/pipeline-fixture-projection.md),
  projection `2d54538` integrated `a6c9e7c`; snapshot/filter fix `14b77f8`
  integrated `224f7f7`. Private PostgreSQL two-session race, 1,002 rows, literal
  $2,002 snapshot total, exact row fields/membership; 83 affected tests. Scratch
  databases removed. This is Pipeline CSV evidence, not Forecast CSV proof.
- **Gap**: [independent inherited-coverage audit](qa-regression-gaps.md),
  `922c4b9`; later explicitly cited repairs supersede individual findings.
- **Ops**: [operations observations and dependencies](operations.md).
  Timestamped remote observations are not new deployment or delivery proof.
- **Baseline**: [S20 baseline reconciliation](baseline.md).
- Full backend evidence at frozen `646419b`: 2,246 passed, one live skip,
  150 inherited xfails ([XML](evidence/baseline/full-0061.xml)). Full web at
  `12d9cd2`: 426 passed in 74 files. Both are corroboration only; they predate
  later fixes. Their totals do not substitute for a condition's assertions.

## S21-01: Permanent SOW Deletion
Scenarios: S21F:T01, T28, T32, T45.

- **verified (local)**: deletion fences, retryable parent cleanup, retained
  financial Project data and exact S3-version removal have real browser/PG/worker/
  storage evidence (`8106641`, `1925e81f`; L). This is not all six lifecycle states.
- **implemented-unverified**: authorized deletion at draft/submitted/review/
  approved/signed/handed-off; one owned-versus-retained manifest and tracked job;
  remove owned uploads, versions, extraction, scope, staffing, GM, approvals,
  SOW actions/comments/renewals and schedules from every count/read surface.
  Exercise the full state matrix, not just hidden-row assertions.
- **implemented-unverified**: cancel tasks/reminders, queued notifications/jobs
  and provider envelopes where supported; prove object-store failure, stale
  worker/callback/key races and retries cannot resurrect or act on the subject.
  Audit/tombstone retains minimal metadata, not document payloads.
- **implemented-unverified**: preserve parent, agreements, other SOWs and
  independent comments/plans; detach and label active Projects, timesheets,
  invoices and actuals; remove only empty Project shells and owned unpromoted
  drafts. Reconcile Archive/reversal behavior with permanent deletion (L).

## S21-02: One SOW Workspace
Scenarios: S21F:T02, T26.

- **verified (local)**: commercial editing is embedded in the existing workspace;
  editor browser evidence `5c9a7fb`, workspace `b991dc6`/`5b46289` (L).
- **verified (local)**: Overview to Staffing & GM to Approvals and Back
  retains one header, tabs, selected SOW/version and exactly one readiness panel;
  deep-link/reload selects the correct tab without escaping the workspace.
  Browser37810 at39f1575, [exact evidence](evidence/baseline/t02-workspace.md).
- **implemented-unverified**: preserve existing state-aware CTAs and source
  filters/navigation context; complete keyboard/focus/responsive journey (L).

## S21-03: Editable Intake And Immutable Revisions
Scenarios: S21F:T03, T28.

- **verified (local)**: confirmation concurrency/source locks are covered by
  `57f7269` and 60 affected tests (L); this is not post-approval reapproval proof.
- **implemented-unverified**: draft values survive forward/Back/completed-step
  navigation, save errors and reload; skipped reviewer selection remains fixable.
- **implemented-unverified**: post-submission material/pricing edits create a new
  draft with reason/change summary, preserve old documents/decisions, and require
  fresh approval authority. Prove approved-to-edit-to-resubmit with navigation.

## S21-04: Honest Facts And Missing Values
Scenarios: S21F:T04, T10, T16.

- **verified (local)**: unsupported/dirty calculation states and first-calendar
  correction are exercised by `5ccabf6`, `5c9a7fb` and `cf51a3ea` (L).
- **implemented-unverified**: distinguish CRM owner from editable local assignee;
  only local assignment may default to uploader. Distinguish Not assigned,
  Not provided, Unavailable and Needs confirmation, without hidden hashes.
- **implemented-unverified**: unresolved year, locale and inclusive date bounds,
  ambiguous pricing, confirmed model/components/term and next action/responsible
  person retain honest evidence and inline correction; names, revision chips and
  saved corrections agree on every reader. Source facts exist in migration0054.

## S21-05: Reviewer Preview Before Submit
Scenarios: S21F:T05, T17.

- **verified (local)**: five-function preview and invalid/stale reviewer guards
  (`7b0ec21`); J executes five actual role decisions through the real application.
- **implemented-unverified**: permitted users can correct eligible reviewers
  after an earlier skipped step; preview shows function, primary/acting reviewer,
  eligibility and routing reason. No mandatory-function or conditional-CEO bypass;
  approval reviewers remain distinct from signature identities.
  Completed constituent conditions: T05 browser89032/a5ee76d verifies direct
  Approvals preview, eligible names, permitted change/submit/reload and exact
  frozen assignments/tasks. Primary/acting/routing-reason and conditional-CEO
  matrices remain unverified; this compound clause is not promoted.
- **blocked**: deployed preview of the actual eligible business roster requires
  account/role readiness. SES verification alone does not confer eligibility;
  dated OOO and override behavior still require verification (S21-06/OP-02).

## S21-06: Business Reviewers And Dated OOO
Scenarios: S21F:T06, T08, T35.

- **verified (local)**: mandatory Sales/HR and frozen routing (`7b0ec21`), with
  inherited conditional-GM/CEO checks identified by Gap; J proves fixture roles,
  not the live named roster or its calendars.
- **implemented-unverified**: idempotently resolve Shawnna/Delivery, Janice/Sales,
  Seema/Legal, Scott/Finance and Al/CEO for floor breaches by real identity, not
  fixed IDs. Preserve existing HR policy throughout schemas/tasks/notifications.
- **implemented-unverified**: Srikanth is Delivery fallback only within explicit
  dated, timezone-aware OOO; test window edges, inactive/missing fallback and
  return to primary. In-flight reassignment is audited and preserves completed
  decisions; no eligible reviewer blocks submission rather than substituting.
- **blocked**: actual roster eligibility and authorized real-recipient delivery
  remain operational checks, distinct from tested fixture routing (Ops).

## S21-07: Trusted Test Isolation And Repair
Scenarios: S21F:T07, T35, T45.

- **verified (local)**: server-issued provenance plus assignment/dispatch/decision
  checks (`bd22cb7`, 130 affected and 13 independent cases, real PG); P grants
  fixture projection without fabricating a HubSpot ID or rewriting source type.
- **implemented-unverified**: exercise the complete real-SOW/test-identity denial
  matrix including forged tags; scan existing contamination, cancel/fence pending
  work and audit eligible reassignment. Deployment enforcement remains unproven.
- **implemented-unverified**: already-recorded invalid decisions require the
  separate authorized invalidation/re-review procedure and downstream assessment,
  preserving historical evidence; pending cancellation is not this proof.

## S21-08: Approval Notification Delivery
Scenarios: S21F:T08, T33-T37.

- **implemented-unverified**: existing outbox/sender, strengthened provenance and
  retry tests (L/Gap) need one complete rejection/timeout/retry/recovery flow with
  one intended notification, dead-letter visibility and safe test recipients.
- **implemented-unverified**: UI/audit must distinguish assignment, queued,
  provider-accepted and delivered, resolve current eligible recipients, and never
  direct automated test approvals to ordinary business users. J uses a sink.
- **blocked**: real account/region/sender/domain coverage, six-person readiness
  and authorized inbox proof depend on OP-01/02/05. Resource creation or SES
  acceptance does not prove verification or delivery; no unapproved outreach.

## S21-09: One Filtered Pipeline Population
Scenarios: S21F:T09, T10, T39, T40.

- **verified (local)**: shared membership/summary/group predicates and stale
  response protection (`a771a37`, 18 independent and 16 owned cases; L). P proves
  exact scoped, filtered, sorted all-page CSV and one PostgreSQL snapshot for
  authorization, totals and row values despite a concurrent reorder/value edit.
- **implemented-unverified**: every view, chip, client matching count, summary,
  group and export uses the same authorized population before pagination; clients
  default to matching deals, sorted by matching count, with explicit empty-client
  option and labelled matching-versus-total-open counts. Complete browser parity.
- **implemented-unverified**: in-place URL chips, multiple pipeline-qualified
  stages and source closed/open metadata, no alphabetical inference; cross-view
  filters retain zero matches. Oldest activity/untouched-14-days distinguishes
  unknown dates. Complete date/saved-view/permission/load cases (L).

## S21-10: Separate Account And Deal Ownership
Scenarios: S21F:T04, T10, T36, T43.

- **verified (local)**: migration0054 and owner/source adapter
  `4ecbd6d`/`83f8bc7`, 59 checks and stale-ORM fence; 11 real-PG source oracles
  in `494ae2e` (L), not live HubSpot parity.
- **implemented-unverified**: company/deal owner IDs and flags stay separate;
  inactive/historical owners remain resolvable, no DealGate login is not a
  missing CRM owner. Show no account owner, unassigned deal owner and unavailable
  metadata distinctly, with local assignee separate on all readers/facets.
- **blocked**: measured current source-to-display reconciliation and named live
  canary parity require authorized provider/source access and OP-04 participation.

## S21-11: Visible Persistent Filters
Scenarios: S21F:T09, T26.

- **verified (local)**: chips, URL wiring, no-match state and refusal of delayed
  old responses have CRM frontend evidence (L); P covers supported CSV filter
  parity and rejects unsupported query keys instead of silently ignoring them.
- **implemented-unverified**: multi-owner/stage/BU, pipeline, open/won/lost,
  attention/SOW-state and created/close/activity date filters; presets 7/30/90
  days/current quarter/custom with validated bounds/timezone; remove-one/clear-all.
- **implemented-unverified**: reload/Back and saved-view replacement retain
  scope; shared URL takes precedence over per-user last filters. Server search/
  sorting and 25/50/100 pagination need stable ties, full-population counts and
  desktop/mobile proof rather than visible-page-only totals.

## S21-12: Names, Labels And Source Metadata
Scenarios: S21F:T10, T17, T36, T44.

- **verified (local)**: source observations, independent ownership and BU mapping
  oracles (`494ae2e`); active facets `e11196e`/`d15dd85`; J preserves named Deal/
  client binding and P labels local origin truthfully without a fake CRM ID.
- **implemented-unverified**: client/deal/pipeline/stage names, amount/currency,
  close date, owner, BU, SOW attention and activity agree across header, breadcrumb,
  table, detail, search and export; legitimate numeric amounts are not treated as
  IDs. Deal detail retains pipeline name even for a single pipeline.
- **implemented-unverified**: discover actual BU property/options and refresh
  stale metadata; absent, empty and inaccessible states explain unavailable
  filters rather than guessing. Current live parity still depends on CO-08/OP-04.

## S21-13: Deal Actions And Comments
Scenarios: S21F:T11.

- **implemented-unverified**: inherited `services/deal_comment.py` and
  `next_action.py` provide relevant tested mechanisms (L/Gap); prove add/edit/
  pin/unpin comments and create/edit/complete owned, dated actions from the real
  Deal UI, persistence, author/time/edit/source attribution and latest activity.
- **verified (local)**: enforce author/role permissions, sanitize rendered content
  and reject stale concurrent writes rather than overwriting another edit.
  [T11](evidence/baseline/t11-tracking.md),43442/1441649 and durable PG69943:
  Sales/HR/unauthorized403, displayed script text, actual simultaneous lock
  waiters and literal winner values with no losing audit/event. Not Cognito/staging.
- **implemented-unverified**: separately attributed CRM notes stay read-only;
  inspect actual endpoints/read scopes, report unavailable access without blocking
  internal comments, and never write staffing/GM into CRM. Existing tests do not
  establish the complete v3 interaction or live notes integration.

## S21-14: Personal Alerts
Scenarios: S21F:T12, T23.

- **implemented-unverified**: inherited scheduler/preferences and
  `test_alert_scheduler` (L) require a complete user-configured application event
  journey: per-deal watch and alerts default off; stage, close-within-14-days,
  overdue actions and applicable renewal/resource reminders. Star is not subscribe.
- **implemented-unverified**: event/subject-version/recipient/threshold keys,
  due-date rescheduling, complete/unwatch/disable/delete cancellation and replay
  deduplication; timezone/channel/digest preferences and delivery-time permissions
  must prevent obsolete sends or financial leakage.
- **blocked**: actual intended-recipient mail evidence depends on OP-02; safe-sink
  verification and independent preference work remain possible meanwhile.

## S21-15: Calendar Staffing Economics
Scenarios: S21F:T13, T19, T21, T22.

- **verified (local)**: deterministic calendar/commercial calculations and frozen
  snapshots (`47119a9`), independent date/money oracles, first-calendar UI
  `5ccabf6`/`5c9a7fb` (L). J independently checks US10,000/4,000 and
  India14,000/6,000 revenue/cost, signed24,000/cost10,000.
  [T13 connected proof](evidence/baseline/t13-calendar.md),00371d2, additionally
  verifies visible/persisted mixed-location hours/holidays and missing-input
  correction;78 current oracle cases pass. This does not close compound clauses below.
- **implemented-unverified**: assignments retain quantity, allocation, bounded
  dates, workweek/shift/location/timezone/calendar and separate billing/cost basis.
  Scheduled, billable and paid hours, caps/minima, leave/holidays, effective rates
  and monthly fixed pricing need full partial-month/part-time/mixed-location proof.
  No invented 160 hours or mandatory manual aggregate; explicit estimates/overrides
  require reason, author and period; absent loaded costs remain unknown, not zero.
- **implemented-unverified**: versioned multiyear country/region/company/client
  calendars, observed holidays/weekends/MSP exceptions, monthly how-calculated
  breakdown and approval-frozen calendar/rate/FX/calculation versions must reconcile
  across profiles and downstream People with local date-only boundaries.
- **implemented-unverified**: US35%/India50% component and package floors cannot
  hide behind blended GM; breached floors require Al and reason. Weighted totals,
  zero/unresolved Not assessed states and frozen policy/exception provenance must
  distinguish planning GM from approval authority throughout the lifecycle.

## S21-16: Extensions And Nonrenewal
Scenarios: S21F:T14.

- **verified (local)**: signed release uses two calendar months, not 60 days;
  `8857936` has five literal month-end/leap-boundary red-to-green cases (L).
- **implemented-unverified**: existing extension lifecycle must prove a new draft
  from signed/released version with term/rate/headcount/scope/fees/obligations/
  calendar changes; show original, proposed, active and delta without duplicating
  original full revenue or accepting overlapping/gapped terms silently.
- **implemented-unverified**: reviews/conditional CEO/signature precede future
  effective activation; original authority remains until ready. Backdated changes
  explicitly handle actuals corrections. One event updates Project term, roll-off,
  Forecast and reminders; reject late obsolete callbacks.
- **implemented-unverified**: undecided/renew-or-extend/not-renew workflow,
  continuing-team identity and delivery through end/closeout; unchanged rates may
  change GM. Complete signed amendment, overlap and nonrenewal journeys remain.

## S21-17: Seven Commercial Models
Scenarios: S21F:T15, T16, T19, T21.

- **verified (local)**: seven deterministic calculators (`2383d0b`), immutable
  schedules (`47119a9`) and structured editors with 40 independent QA cases;
  browser repairs `5c9a7fb`/`cf51a3ea` (L). J proves one fixed-fee hybrid, not seven
  end-to-end profiles. Unknown models remain explicit, not forced into staffing.
- **implemented-unverified**: separate delivery workstreams, commercial profile,
  term/cadence/cost dimensions; registry validation/editors/calculation must use
  deterministic supported formulas, never LLM-generated arithmetic. Confirm
  incomplete inputs without inventing costs, dates, currency or hours.
- **implemented-unverified**: fixed assignment allocates total fee once across
  service/milestones (installments separate); recurring MSP handles proration,
  credits, usage, coverage and setup with night/weekend/holiday/SLA costs; staffing
  uses calendar quantity/rates and distinct scheduled/billable/paid time. Prove all
  three through upload, corrections, approval, signature and monthly delivery.
- **implemented-unverified**: milestone acceptance/planned/invoiced/recognized
  timing stays distinct from delivery costs; T&M preserves rate units, caps,
  minima and estimate-versus-actual usage; unit/story-point pricing preserves
  accepted versus estimated units without universal hours conversion; hybrids
  conserve dates/currency/units/one-time fees/shared cost and per-component GM.

## S21-18: All-Model Intake And Migration
Scenarios: S21F:T15, T16, T27-T29.

- **verified (local)**: structured editors and explicit incompatible-model switch
  confirmation; manual extraction preservation `48f47f4`/`57f7269` (L). J validates
  typed personal signatories against real extraction and matching signed bytes.
- **implemented-unverified**: all seven profiles traverse upload/extract/correct/
  confirm/scope/financial review/sign/handoff/amend/forecast, including tables and
  hybrids; evidence, overrides, impact summaries and immutable signed history
  survive model changes. Unknown logic is a preserved needs-confirmation draft,
  not a claim that arbitrary pricing is supported.
- **missing**: primary OCR path remains unfinished (L). Complete scan and held-out
  ambiguous/hostile fixtures, missing-year/currency/fee exceptions and targeted
  corrections without discarding uploads or allowing unresolved approved inputs.
- **implemented-unverified**: legacy deterministic mapping reports mapped/unknown/
  missing-cost/date counts, flags ambiguity without rewriting historical values,
  and survives representative backfill/restore rehearsal and concurrent activity.

## DG-01: Groups And Watchlists
Scenarios: S21F:T12, T39.

- **verified (local)**: dynamic group membership no longer truncates at 200
  (231-member case), and group/watch intersections share Pipeline predicates (L).
- **implemented-unverified**: persistent validated rules versus manual client/deal
  watchlists retain owner/visibility/entity type, pipeline-qualified stages,
  selector/command counts, stable manual membership and saved views.
- **implemented-unverified**: membership never grants record access or ownership;
  delete/merge reconciliation and event-driven updates obey authorization. Lead
  is proving the zero/one-in-three-groups/unwatch browser case separately.

## DG-02: Consistent Client Summaries
Scenarios: S21F:T10, T17, T40.

- **verified (local)**: shared filtered population, live SOW rollup and closed-won
  attention corrections have 18 independent CRM cases (L).
- **implemented-unverified**: named client/HubSpot link/account owner, NDA/MSA
  uploads, open count/value, activity, files and named opportunities reconcile;
  each opportunity shows correct stage/currency/date/owner/BU/SOW state/action.
- **implemented-unverified**: worst-open/closed/archived distinctions and zero
  counts agree across detail, card and destination under identical source scope.

## DG-03: Navigation Context
Scenarios: S21F:T02, T09, T17, T26.

- **verified (local)**: Pipeline URL/chip/delayed-response behavior and workspace
  editor paths have bounded UI/browser evidence (L, W415 and `5c9a7fb`).
- **implemented-unverified**: Pipeline/client/deal/upload/workspace deep links
  and return paths preserve filters, page, scroll and source; no approval-only
  alternate workspace. Complete cross-view, reload, Back and accessibility proof.

## DG-04: Deals Without Synthetic SOW Stubs
Scenarios: S21F:T17, T27, T41.

- **verified (local)**: J enters the exact authorized Pipeline fixture, reads the
  same Deal/client and uploads a bound SOW without pretending it is live CRM;
  inherited upload-binding and true-SOW-ID tests are recorded in L.
- **implemented-unverified**: dedicated Deal route shows actual pipeline/stage,
  agreements, actions/comments/alerts and linked plans; no-SOW state exposes
  Upload, not Delete/readiness/stepper. Every SOW retains independent versions,
  gates and reviews, distinct from sales stage.
- **implemented-unverified**: prelinked upload retries/interruption leave one
  stored draft without orphan/duplicate; sync never creates empty SOW stubs.
  Inventory existing stubs and perform idempotent dry-run/reviewed cleanup only
  for proven empty records; flag ambiguous rows rather than delete by appearance.

## DG-05: Client Agreement Document Store
Scenarios: S21F:T01, T17.

- **implemented-unverified**: previously missing replacement/version lineage and
  shared Client/Deal/SOW/scoped-register presence now integrated7cbdac7 with UI
  3c9152d/bd802fe/400eb91 and fixture guards65b2ca7. Six final API cases16723,
  worker UI/tsc and real PG migration/CAS/deletion race72731 pass. Current integrated
  browser59018 now establishes both uploads, four-surface presence, replacement
  and historical real-S3 bytes/hashes; it failed only at final signed-URL equality,
  corrected read-only61252 establishes source preservation. Missing connected
  absent/NDA-only states and bound Upload/View entry actions remain; no parent closure.
- **implemented-unverified**: presence is not legal execution status or an
  approval/signature gate; SOW deletion preserves client agreements. Complete
  four-surface and deletion journey, not a new agreement-tracking workflow.

## DG-06: Governed SOW Through Delivery
Scenarios: S21F:T02, T03, T17, T41.

- **verified (local)**: J executes five reviews, matching signed bytes, accepted
  handoff and real Project/Forecast/actuals on one source; editor/workspace and
  release/idempotency tests add bounded evidence (Gap/L).
  Fresh browser96337 at f74df88 adds uninterrupted real-provider empty-deal-to-
  handoff proof, exact24k/10k economics and five distinct persisted reviewers;
  it does not independently extend that new browser proof into Forecast/actuals.
- **implemented-unverified**: all eight tabs share names/version/status, one
  readiness panel and Intake/Scope/Reviews/conditional-CEO/Signature/Handoff
  progression with responsible owner, reason blocked and existing next CTA.
  Readiness28000/93052 and browser94587 now verify the released current-package
  gate, visible responsible owner and existing action; earlier-state state logic is
  focused-tested, while current-revision route inventory remains outstanding.
- **implemented-unverified**: material edits invalidate authority via immutable
  new packages; callback identity/version/state and retries permit one Project.
  Handoff carries term/scope/resources/costs/obligations/source and effective
  amendments; unsigned Forecast is not delivery commitment. All read services,
  rename/delete propagation and errors stay consistent, never fake empty success.

## FC-01: Five Forecast Views
Scenarios: S21F:T18, T26.

- **verified (local)**: Company & accounts, Revenue projection, Overview, Next
  opportunities and Resource demand are implemented with persisted APIs and local
  browser evidence (`a1354ea`, `2d9fc16`/`d3e4fa0`, `351ed9b`, `ccc539b`; L).
  T18 now verifies persisted all-view scope/month/scenario navigation, populated
  Overview, assumptions, publication/coverage/history/pagination, source links,
  CSV and empty/error recovery through finalad30e77/8316; detailed condition
  mapping in [T18 proof](evidence/baseline/t18-five-views.md).
- **implemented-unverified**: accepted preview layout in the existing shell,
  Company default, visible scope chips/saved views/drilldowns/assumption edits/
  automation/exports all perform real actions without localStorage as the source
  of truth. T18's bounded controls/empty-error clauses above are now verified;
  the remaining full parent permissions, renewal/linkage, saved views/automation
  and desktop/mobile matrix are not closed by that scenario.

## FC-02: Company Outlook
Scenarios: S21F:T18, T19, T21.

- **verified (local)**: independent Company X Expected196,000 to140,000 after
  probability change and nonblank chart (`43cbb8c`); J independently checks
  signed24,000/cost10,000, zero potential and 15 months on its fixed-fee fixture.
  T19 additionally verifies accepted12source/6account/15month/5quarter/3scenario
  literals25684 and realUI date/value/probability edits54224/93529 on44fec51;
  [proof](lanes/t19-plan-terms.md). Broader clauses below remain separate.
- **implemented-unverified**: current month/current quarter stay separate from
  next two full quarters by default; support 1/2/4 future quarters and month
  drilldown, live as-of/organization timezone/calendar-quarter basis. Oct1 must
  not count current Q4 as a future quarter; fiscal policy cannot change silently.
- **implemented-unverified**: signed/potential/scenario cards and charts, future
  coverage/cost/GM, renewal dependency, expiring unreplaced work and concentration
  reconcile under accepted six-account fixture. Labels expose period/currency/
  accounting basis; selected accounts/My portfolio are not mislabeled Company.

## FC-03: Account Outlook
Scenarios: S21F:T18, T19, T25.

- **verified (local)**: 15-month account drilldown, evidence/source rows and scoped
  CSV have browser evidence `e8eeb9e`; J checks same-source signed schedule (L/J).
  T19 now proves all six account sums and post-edit account/company reconciliation.
- **implemented-unverified**: current month/quarter/future coverage drill to SOW
  components, growth assumptions and staffing/evidence; preserve account/period/
  scenario and reconcile pre-round account sums to company, including accounts
  with current work but no future work. Edits must update all views and demand.
- **implemented-unverified**: accepted preview's complete population, restricted
  account navigation and export/deep-link scope: full preview population is now
  proved byT19; broader restricted navigation/export scope remains.

## FC-04: Monthly Source Schedules
Scenarios: S21F:T18, T19, T21.

- **verified (local)**: persisted plan and commercial schedules (0050/`47119a9`)
  and independently calculated Company X; J checks fixed-fee hybrid source/version,
  signed total and same baseline after actuals corrections.
- **implemented-unverified**: every commercial profile allocates monthly revenue/
  cost with model/status/probability, full-term versus selected totals, traceable
  source/version/assumptions; signed, tentative, won-unsigned, unresolved and
  excluded rows are distinct. Account/owner/BU/pipeline/stage/model/status/period
  filters must not change the underlying schedule logic.
- **implemented-unverified**: expiry/renew/extend/upsell/cross-sell/no opportunity/
  undecided/nonrenewal and follow-on links reflect actual decisions, not invented
  opportunities. Overview expiry decision and assessment paths reuse these facts.

## FC-05: Scenarios And Economic Deduplication
Scenarios: S21F:T19, T20, T21.

- **verified (local)**: immutable plans and conversion guards
  (`dd4ac6d`/`ee4659c`), independent QA and Company X probability-change journey
  establish bounded potential weighting/replacement behavior (L).
- **implemented-unverified**: Committed includes active signed schedules;
  Expected weights eligible unsigned revenue/cost once, Upside uses full value;
  unavoidable costs are explicit. Confidence is not probability. Missing probability
  is unknown; provisional needs-review numeric rows are separate, incomplete rows
  explain exclusion, lost/dismissed/expired excluded, won-unsigned not signed.
- **implemented-unverified**: canonical economic scope replaces potential once on
  conversion, including partial residuals, multiple SOWs, mutually exclusive
  options, amendments and repeated CRM sync. CRM amount is not automatic service
  revenue; no full Deal value copied into each SOW.
- **implemented-unverified**: Decimal conservation, original currency/FX rate/date
  and unresolved missing FX; versioned recalculation without rewriting old
  snapshots. Same-period coverage ratio has N/A zero basis, GM is weighted with
  honest missing cost, and concentration uses the stated denominator.

## FC-06: Actual Financial Results
Scenarios: S21F:T21, T25, T41.

- **verified (local)**: validated four-basis import/corrections with real PG Numeric/
  concurrency and HTTP/browser (`0051`, `e8eeb9e`, `f944daa`). J imports same signed
  Project actuals, replays idempotently and corrects recognized12,000.01 to11,000.99;
  billed15,000/cash8,000/cost6,000 remain distinct and original schedule/GM retained.
  T21 now also proves matched certified coverage replacement and correction:
  19ca6f7/76926/11028/33980, literal23000.99/11000 ->22500/11000, PG races,
  immutable history, separate invoice/cash and responsive display.
- **implemented-unverified**: reconcile legacy ActualPeriod, connector inventory/
  source ownership, permission and correction history across all bases and periods;
  identify managed imports as imports, not a fictitious live Finance connector.
- **missing**: full actuals import UI remains unfinished in L. Invoice must not
  silently become recognized revenue; absent actuals show signed schedule plus
  unavailable state, not invented actuals or full-period double counting.

## FC-07: People Supply, Demand And Sourcing
Scenarios: S21F:T22, T23, T25.

- **verified (local)**: managed supply and global allocation (`0056`-`0059`,
  `7f98459`), seven-head 70%-to-40% probability browser proof; coverage4-to-2-to-4
  and PG locking (`da6ca77`, `81278e1`), retained deletion `681835e` (L).
- **verified (local)**: J publishes the same released Project with two US/five
  India people, detects missing capability, accepts evidence-backed enrichment,
  and a separate worker produces a complete seven-head draft with September1
  sourcing deadline and unchanged history; replay creates no duplicate draft.
- **implemented-unverified**: complete role/skills/level/location/timezone/dates/
  allocation/model/owner/source demand by month, headcount versus FTE; tentative,
  committed, reserved and hired distinct. Supply import/source freshness and
  global capability/date/capacity matching must handle part-time/roll-off/overlap
  without allocating one person twice or treating a match as reservation.
  Completed constituents: T22 browser84625/e879213 plus27 current capacity
  tests96252 prove exact half-time2.5FTE matches/1FTE gap, overlap/roll-off and
  same-plan continuity; unchanged through70->40% and sourcing history. Complete
  lifecycle/model/source/freshness matrix remains; compound clause stays open.
- **implemented-unverified**: configured skill/location lead times (45/30 only
  explicit starter policy), continuing named team versus incremental hires, unchanged
  six-person extensions, changed term/probability/staffing/nonrenewal event history.
  People shows account/likely start/skills/full quantity/probability/status/link;
  idempotent sourcing and permission-aware preference alerts never reveal costs.
  Completed constituents: T23 admin88901/Sales49160/23dffd9 proves API-authored
  start/headcount revision -> browser republish/sourcing, immutable old lines/
  draft, populated cost-free Sales view and unchanged workforce under success/
  forbidden action requests. Automatic event/preference/extension breadth remains.

## FC-08: Next Opportunities And CRM Linkage
Scenarios: S21F:T20, T23, T24.

- **verified (local)**: Next opportunities and persisted versioned assumption/
  probability editing (`ff8d10f`, `351ed9b`, 34 API/22 UI and real worker/browser;
  L); J carries source identity into Project demand. Local linkage is not CRM write.
- **implemented-unverified**: canonical account and optional source SOW, authorized
  CRM identity matching/review or explicit Local forecast only; no similar-name
  duplicate, inferred CRM ID or implicit mirror write. Link existing usable import/
  promotion paths; report unavailable CRM writes instead of fabricating success.
- **implemented-unverified**: complete Company X four-week to six-month next-month
  plan, seven roles/two US/five India, evidence-backed assumptions, HR publication,
  opportunity linkage/conversion and slipped-date revenue/quarter/sourcing update.
  Local Sales/Delivery planning never commits business without authorized action.
- **missing**: automatic opportunity generation remains unfinished per L; existing
  persisted plan editing is not automatic candidate creation or signed conversion.

## FC-09: Extraction Evidence And Review
Scenarios: S21F:T16, T24, T26.

- **verified (local)**: source-token exception review (`e75af5c`), CAD correction
  browser (`0cbb530`), sibling draft invalidation (`8d4e5f4`, seven unit tests),
  backend locking (`12d9cd2`, 56 cases; `8476f3b`, four real-PG races). J confirms
  typed personal signatories from real Bedrock and matching signed-document check.
- **implemented-unverified**: extract model/pricing/term/units/staffing/milestones/
  coverage/renewal/obligations with page/cell/hash/document/extraction version;
  distinguish extracted from inferred. Prefilled queue supports targeted correction,
  reject/dismiss/defer/noncritical bulk actions, evidence and missing/conflict
  reasons; material inputs require confirmation and re-extraction preserves overrides.
- **missing**: primary OCR and extraction-attempt history remain unfinished (L).
  Scans/tables, ambiguous originals and held-out corpus need real evidence, not
  corrected synthetic outputs alone.
- **implemented-unverified**: findings/scope/progress/CRM signals may produce
  explicitly assumed follow-on candidates, never invented skills/rates/commitments
  or policy changes; broader exception permissions and fresh browser parity remain.

## FC-10: Persistent Safe Automation
Scenarios: S21F:T16, T23, T24.

- **verified (local)**: rules/outbox/worker/UI0060/61, fanout `fcabb6e`, Project
  event `31816c9`, real PG crash recovery and browser9704 (L). J observes worker
  runs2/1/0, review-to-complete enrichment, exact seven heads and immutable history.
- **implemented-unverified**: configured rules govern upload/extraction, amendment/
  source refresh, renewal/growth/HR notification domains, thresholds and schedules;
  visible job/last-success/retry/stale state. Disable and change rules through real
  UI and prove worker behavior on the same source; no implicit irreversible action.
- **implemented-unverified**: untrusted-document handling, strict schema and
  deterministic document-hash/extraction/prompt/schema-version idempotency,
  bounded retries and override preservation across upload/re-extract; measured
  confidence distinct from probability, completeness and readiness.
- **implemented-unverified**: held-out all-profile/scanned/conflicting/unknown/
  malicious corpus with critical-field and evidence metrics, all critical review/
  correction and a separate small staging live-model evaluation. No claim of
  calibration from fixtures, and no automated irreversible business commitments.

## FC-11: Forecast Exports And History
Scenarios: S21F:T25.

- **verified (local)**: scoped Forecast CSV/browser and immutable schedule/history
  evidence `e8eeb9e` (L). This is a bounded account drilldown, not all-row/role proof.
- **implemented-unverified**: same authorized population/scenario across every page
  at identical snapshot; export period/timezone/currency/FX/as-of/actual-versus-
  forecast/calculation version and preserve dated snapshots for comparison.
- **implemented-unverified**: formula-injection protection and field/record/tenant
  restrictions, including HR/recruitment costs/rates and historical deep links.
  P's Pipeline CSV fix does not establish this separate Forecast endpoint condition.

## FC-12: Consistent Recompute And Authorization
Scenarios: S21F:T25, T28-T31.

- **verified (local)**: persistent jobs/retries and separate worker replay1/0/1,
  0061 crash rollback/recovery (L); J source-bound release/enrichment fanout and
  replay preserve prior schedules/drafts and unchanged actuals baseline.
- **implemented-unverified**: transactionally publish every relevant source change,
  deterministically deduplicate/out-of-order/obsolete events, bounded retry/dead-
  letter recovery; invalidate account/company/People caches by tenant/permission.
  Source watermarks must not present incompatible snapshots as a fresh total.
- **implemented-unverified**: server authorization of reads/edits/deletion/reviewer
  overrides/exports/admin rules, Sales commercial scope and HR demand-only scope;
  direct API/shared-link/aggregate field and record isolation. Complete event graph,
  stale/concurrent cases and stated load target (10,000 Deals, 1,000 SOWs, 24 months
  or larger actual volume; p95 lists2s/summaries3s with hardware/concurrency reported).

## OP-01: Infrastructure And Sync Monitoring
Scenarios: S21F:T33, T42.

- **implemented-unverified**: inventory, state-adoption imports, paired cutover,
  IAM/heartbeat and module preparation exist (27 consumer checks/two TF tests;
  Ops). Current plan is explicitly not approval-ready; prepare exact commit/image,
  whole-root addresses/diff/side effects/add-change-destroy and explain drift.
- **blocked**: verified backend/workspace/account/region with locking and repository
  wrapper, reviewed exact plan and required human apply confirmation; no agent
  yes/auto-approve/saved-plan bypass. Separate planned/awaiting/applied/verified;
  partial failure requires state inspection/re-plan, not assumed rollback.
- **implemented-unverified**: heartbeat/queue-age/repeated-failure/dead-letter
  monitoring needs thresholds/windows/missing-data/destination/runbook, measured
  UI freshness, safe quiet/stalled/delayed/recovery proof and actual notification.
  A resource alone or old success sample is not a healthy consumer (CO-06/OP-04).

## OP-02: Regional Mail Readiness
Scenarios: S21F:T34.

- **implemented-unverified**: Ops records regional sender/sandbox/identity gaps
  and delivery preparation. Refresh time-stamped coverage for all six named
  recipients, checking verified domains before redundant individual identities;
  keep role eligibility, identity creation, verification and delivery separate.
- **blocked**: approved missing-identity setup, recipient verification where needed
  and explicitly authorized intended-inbox check. Track method/status/last-check/
  action, do not resend invitations each deploy or send unapproved communications.
- **blocked**: sender to outbox/worker/SES/inbox, provider message ID and delivery
  evidence, suppression/bounce/failed-send verification. Aliases and resource
  creation are not proof of readiness; routine tests retain safe sinks/simulators.

## OP-03: Liberty Approval Recovery
Scenarios: S21F:T35.

- **implemented-unverified**: Ops records remote API observation of the precise
  cycle already voided and no active assignments. This is an observed condition,
  not combined-staging validation or proof of downstream DB/outbox cleanup.
- **implemented-unverified**: audit exact account/Deal/SOW/version, test Finance
  assignment, decisions/notifications/downstream effects; preserve file, money and
  history. Test stale-task/callback fencing and repair on isolated fixtures; use
  separate invalid-decision handling if needed. Do not cancel a valid cycle again.
- **blocked**: real eligible roster preview and intentional PO resubmission once,
  correct linked superseded version/cycle/tasks/submitter/activity/status and retry
  singularity. Expose email limitation under actual submission policy, never use
  a test reviewer to solve missing role or mail readiness.

## OP-04: Human HubSpot Canary
Scenarios: S21F:T36, T42, T44.

- **blocked**: authorized human saves a clearly named canary in the agreed portal
  after ready deployment; record synchronized UTC source-save t0 and ordinary UI
  visibility t1 <=120 seconds with no manual sync/reimport/direct DB shortcut.
  Protocol exists but the operational action has not been executed (Ops).
- **blocked**: compare owner/pipeline/stage/amount/currency/close date, BU or honest
  absent state, association/counts/filter/source timestamps/no empty SOW; update
  stage/date, prove propagation/no duplicate, record worker/build correlation and
  agreed source cleanup/reconciliation. Missed target needs diagnosis and retest.

## OP-05: SES Production Access
Scenarios: S21F:T37.

- **implemented-unverified**: truthful regional transactional request draft exists
  (Ops), including application URL, expected volume/recipients and only implemented
  bounce/complaint controls. Sandbox observation is not a submitted request.
- **blocked**: authorized account operator submits under approved workflow; AWS
  outcome is external. Record pending/denied next action, not a promised 24-hour
  approval or a five-user rollout heuristic.
- **blocked**: after approval, verify account status/authentication/quotas/rate
  controls/outbox and controlled non-sandbox-dependent delivery; until then retain
  verified-recipient and quota constraints and tracked backlog/owner.

## CO-01: S20 Baseline And Main Image
Scenarios: S21F:T38.

- **verified (local)**: repository main/tag `321b365` and ancestry were reconciled
  in Baseline; no repeated S20 merge or assumption that old merge proves runtime.
- **implemented-unverified**: maintain full baseline/descendant delta and preserved
  dirty worktrees/branches/tag, retained `33c38a0` history and immutable image/digest
  binding. Historical deployment70/image `s20-27e2edec` is not a prescribed revision.
- **blocked**: final exact-main-image check-only smoke and UI/API/worker/schema
  parity remain unresolved: observed smoke extraction failed against older image
  (Baseline/Ops). Controlled approved deployment and fresh stable-task evidence
  are required; an old completed poll ID or shell success is insufficient.

## CO-02: Legacy Reconciliation And Combined Regression
Scenarios: S21F:T38 plus mapped legacy S20 IDs.

- **verified (local)**: 65 legacy rows are separately inventoried (L/Gap); frozen
  backend646419b ran2,246 pass/one live skip/150 inherited xfail and web12d9cd2
  ran426 pass. These runs explicitly predate later changes and are not final gates.
- **implemented-unverified**: preserve every original row/evidence/owner/CO link,
  namespace S20 T32/T34/FINAL-T38 and inspect A1-A4 artifacts. Correct local auth/
  fixture/CI selection without filename-based staging bypass or blanket xfail removal.
- **implemented-unverified**: root-cause inherited t09/t40/order/ownership failures,
  replace unresolved rows with actual assertions and reasons for every skip/xfail;
  run full backend, scoped Playwright/security and serial staging on the final
  combined revision. Isolated passes or suite counts alone do not reconcile rows.

## CO-03: Distinct Watching Count
Scenarios: S21F:T39.

- **verified (local)**: shared authorized group/watch membership and exact HTTP
  Deal/client results are covered by CRM lane evidence (L).
- **verified (local)**: browser46207 at941953a shows empty0, one watched Deal in
  three groups with exact card/list identity and total1, then unwatch0, including
  restricted-record filtering. [Full evidence](evidence/baseline/t39-watching.md).
  Group memberships are not Deal count. Combined staging proof remains required.

## CO-04: Approval Card Population
Scenarios: S21F:T40.

- **verified (local)**: live SOW newest-nonvoided package rollup and archive/
  superseded exclusions have independent CRM tests (L).
- **verified (local)**: mixed draft/in-review/approved/restricted/zero fixture
  reconciles exact card-to-approvals destination membership under the same
  authorization/filter/snapshot; multiple reviewers count once, two SOWs under
  one Deal count twice. This is not generic Pipeline attention or a formatting test.
  Browser99369 at205d51a plus47 affected API/5 UI tests and independent QA;
  [snapshot and membership evidence](evidence/baseline/t40-approval-card.md).
  Combined staging verification remains outstanding.

## CO-05: Connected Signed Delivery And Actuals
Scenarios: S21F:T41, T17, T21; legacy S20:t44-full-journey retained.

- **verified (local)**: J proves authorized Pipeline fixture to same Deal, real
  upload/extraction, five decisions, verified signed bytes, release/acceptance,
  one Project, Forecast and same-Project four-basis actuals/replay/correction;
  real PG/S3/Bedrock/separate workers with literal financial/headcount expectations.
- **implemented-unverified**: full browser flow, wrong-version/wrong-signatory
  negatives, repeated handoff singularity, exact period/basis/account/company/GM
  reconciliation and isolated leak-free teardown still need combined scenario
  evidence; preserve legacy namespace rather than silently skipping it.
- **blocked**: staging real-user/Cognito, configured provider contract and authorized
  inbox boundaries require ready release/access; J's local auth and SES sink do
  not close them. Real source documents must match version/terms/signatories.

## CO-06: Consumer Drift And Freshness
Scenarios: S21F:T42, T33, T36.

- **implemented-unverified**: Ops inventories six old worker images/absent service
  and prepared paired cutover. Inventory is not actual consumer processing;
  historic approximate resource counts do not prescribe the new plan.
- **blocked**: exact-image whole-root adoption plan with remote backend/locking,
  account/region/wrapper, imports and rollback must receive OP-01 human approval.
  No state reset, force-unlock or target masking of unrelated drift.
- **blocked**: approved deployment followed by consumption/queue age/retry/
  reconciliation, quiet/stall/recovery alarm delivery and normal-sync human canary.
  If pending, expose active sync mode honestly; a running task alone is not lag proof.

## CO-07: Durable Metadata And Recovery
Scenarios: S21F:T27-T29, T43.

- **verified (local)**: migration0055 (`d596dd9`/`168b605`), atomic scan `1c5b245`,
  independent QA repairs `8bd6da6` with82 cases and real PG lock/rollback/resume (L).
- **implemented-unverified**: stage rename and company/Deal reassociation preserve
  source-correct labels, names/counts/membership and provider parity, including
  repeated/out-of-order events without duplicate effects.
- **implemented-unverified**: independent-process kill at checkpoint/commit,
  same-generation restart, complete deduplication and safe malformed/concurrent
  rows, no false tombstones on incomplete scans, deletion/reassociation/dead-letter
  recovery and stage-qualified-key cutover. Remove only individually disproven
  inherited xfails; deploy/recovery evidence remains outstanding.

## CO-08: Real BU Availability
Scenarios: S21F:T44, T10, T36.

- **verified (local)**: migration0054 source adapters and11 real PG oracles
  `494ae2e`; active facets `e11196e`/`d15dd85` with38 API/five UI cases (L).
- **implemented-unverified**: configured, absent, empty and inaccessible property
  states persist with correct labels/disabled filters; actual property name/type/
  options/owner are requested, not guessed or automatically created. Settings,
  mapping/backfill and account/company grouping retain explicit unclassified rows.
- **blocked**: current authorized live metadata and human canary parity (including
  verified absence) remain distinct from synthetic adapters; no false live-BU claim.

## CO-09: Safe Fixture Cleanup
Scenarios: S21F:T45, T01, T32.

- **verified (local)**: trusted provenance/age selector `4c137b8`, 46 affected QA
  cases `8106641`, real parent cleanup preserves Project/actual24680.125 and removes
  exact S3 versions (L). These are bounded isolated fixtures, not a staging sweep.
- **implemented-unverified**: minimum24-hour trusted tenant/environment/run age,
  null-ID insufficiency, invalid/negative age rejection, explicit scoped zero-age
  only; protect young active/untagged/mirrored/real-name-collision records. Preserve
  prior nonmirror cascade/mirror refusal and minimal client_name audit.
- **implemented-unverified**: dry-run dependency manifest, permission/storage/
  outbox/task graph, failure isolation, retries and no resurrection; client delete
  retains active financial history. Record exact eligible/leaked/deleted counts
  and staging gate; user-requested deletion is not automatic fixture authority.
- **blocked**: scheduled activation remains default disabled pending its approved
  scope; no inferred permission to run a broad production or staging cleanup.

## CO-10: Product Owner Acceptance
Scenarios: Gate5 / FINAL-CLICK, using S21F:T01-T45 evidence.

- **blocked**: finish combined engineering/operational release gates, deploy exact
  revisions and offer real named Deal/filter/card/SOW/GM/review/delete/signature/
  Project/actuals/Forecast/People/canary click-through without fixture leakage.
  Actual human acceptance has not occurred; historical S20 permission is not S21.
- **blocked**: PO staging click-through and explicit merge approval, followed by
  resulting main-image verification. Keep consumer apply, regional recipients,
  SES production access and BU dependencies visible with owners through OP-01-05;
  do not count them again as separately completed features or reuse old FINAL-CLICK.

## Interpretation And Remaining Ambiguities

- Coverage inventory: S21 18 IDs, DG six, Forecast12, Operations five, S20 carryover10:
  **51 original requirement IDs**, none removed or renumbered. No condition here
  declares a parent complete; no manufactured fractional completion estimate.
- Some compound implementation gaps are not yet resolved into missing versus
  merely unverified code. Those are explicitly implemented-unverified, with the
  required business result stated. The lead must inspect/prove them before changing
  state; test absence is not evidence of absent functionality.
- The contract permits managed Finance/People imports when no connector exists;
  lack of a live connector alone is not missing scope. Actual-to-date overlay,
  import UI, primary OCR/attempt history and automatic opportunity generation are
  specifically identified unfinished capabilities, not inferred from that choice.
- Real roster eligibility, SES verification and mailbox delivery are independent;
  HR policy remains preserved. Approved calendars/FX/accounting definitions and
  actual BU property availability cannot be invented from fixtures.
- Local fixture projection proves safe Pipeline/Deal continuity, not HubSpot sync.
  The human source canary, full current-image smoke, final combined regressions,
  staging evidence and explicit merge acceptance remain separate gates.
- Shared integration/migration obligations in V3 remain cross-cutting: additive
  reversible migrations, resumable counted backfills preserving overrides, isolated
  backup/restore rehearsal, compatible API/worker ordering, reviewed cleanup,
  correlated observability, provider scope/signature verification, pagination,
  rate-limit/retry/outage reconciliation and measured load. Refer to CO-01/02/06/07/09,
  FC-09/12 and OP-01 rather than inventing additional requirement IDs.
