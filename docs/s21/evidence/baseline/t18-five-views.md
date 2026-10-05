# T18 Five-View Evidence

## Current State

2026-10-03 02:16 UTC. Latest applicationad30e779c7adb6f48e230846612ac4cb35ad1fdb.
T18 CLOSED LOCALLY: all six original conditions verified. Eleven scenarios
passed locally; no parent requirement promoted. Prior fa0c787 executions below
cover unchanged financial/navigation behavior;ad30e77 only adds async anchor reveal.
No S21 staging deployment, infrastructure mutation or main merge.

| Original condition | Attributable proof |
| --- | --- |
| .01 persisted five views | 25161 and99259 populated Overview |
| .02 company/account/source/month drill | 25161/99259 |
| .03 scope/period/scenario retained | 25161/32834/8316 |
| .04 current quarter separate from future | 25161/99259 independent literal totals/rollover |
| .05 names and honest empty/error states | 67649 empty/error case;99259 resource endpoint recovery |
| .06 visible controls | 25161 shared navigation/CSV;99259 edit/publish;31702 mapping/history;32834 source paging/links/disclosure;69292 exact clear/restore prefix;8316 project-demand anchor/Back |

Final browser8316 PASSED1/33.8s (test28.1s), exact source in viewport and
Back context. [Link proof](t18-project-link-proof.json),
[inspected image](t18-project-demand-link.png).34 affected UI79245 passed;
typecheck77526 exit0. No finite test active. Runtime remains isolated local0062.
T18 fixture accountC currently51 plans, both publications current, mappingrev53.

## Supporting Execution History

- UI41393:26 passed, two affected files; typecheck76705 exit0.
- API4816:5 passed, [XML](t18-empty-account.xml).
- Fixture99198:exit0; two API-created plans calculated by separate worker10265,
  handled2/exit0. Receipt `/tmp/s21-five-views-20261003.json` must not be overwritten.
- Browser67649:1 passed/1 failed,52.5s. The passing40.5s case verifies all five
  empty views show the real authorized account name, distinguish transport
  failure from empty data, disable export on error and recover by explicit
  Refresh. [Screenshot](t18-empty-recovery.png) visually inspected.
- Populated journey fails BEFORE UI navigation: expectedfuture360, received0.
  [Actual response](t18-fixture-exclusions.json) records six excluded rows with
  absent staffing cost_rate/cost_version. This is a fixture prerequisite defect,
  not evidence the expected forecast passed. No weaker expected total accepted.
  Repair1195 has now passed: both plans revised immutably, hourlycost1/version
  plus distinct monthly overhead; actual worker recalculated and literal360
  passed. Receipt `/tmp/s21-five-views-repair-20261003.json`. Browser25161 now
  ran only the failed populated case and PASSED1/1.2m (test1.1m): allfive tabs,
  named account/source, month selection, scope/scenario/period, Back, CSV and
  exact independent24000/300/360/840/0. [JSON](t18-views-proof.json),
  [desktop](t18-views-desktop.png), [mobile](t18-views-mobile.png), both inspected.
  No reseed, deletion or expected-value change.
- QA requires strengthened populated Overview, persisted assumptions/lifecycle,
  resource-specific error, date-rollover and expanded coverage-control assertions.
  Controls99259 PASSED1/1.5m: populated Overview100, source/account drill,
  quarter rollover300/0; cancel and invalid probability unchanged; changed
  won_unsigned/source/assumptions persisted, real worker recalculated360;
  publication skills/Senior/revision binding persists and own endpoint recovers;
  dated A/B demand filters and unweighted headcount; restoreversion4/.5/jobdone/
  exact300. [Control operations](t18-controls-proof.json). Expanded coverage
  controls then pass31702 (1/51.9s): actual UI enrichment,
  Analyst second-slot mapping/partial dates, persisted7heads then clear8heads,
  51 immutable revisions, history selection and both page directions.
  [Coverage proof](t18-coverage-controls-proof.json), [history image](t18-coverage-history.png).
  QA found every() could accept an empty interval population;69292 now verifies
  exact five monthly/coverage intervals8/7/7/8/8, UIclear52 ->three monthly8/8/8,
  restore53 ->original exact five intervals. [Exact proof](t18-coverage-clear-proof.json).
  This run then failed an incorrect project-detail route assertion; do not
  rerun its mutation precondition. Intended link is People Demand source.
  Source paging fixture96169 passed:50 dismissed plans plus existing mirror,
  all50 jobs done, unchanged mirror version. Receipt
  `/tmp/s21-five-views-paging-20261003.json`. Browser32834 paging case PASSED
  1/57.2s: both enabled page directions, unchanged900 accountC future economics,
  deal links/Back, and actuals-exception disclosure. [Paging proof](t18-source-paging-proof.json).
  Readonly29263 identifies remaining real defect: People Demand source is loaded
  after native fragment navigation and remains outside viewport. Anchor repair
  ad30e77/8316 now resolves it; original failure retained. No feature responses mocked.

## Owned Data And Recovery

Database `s21_cov_37ebcb10ed7f4528b7f34c846fed747b`, owner s21,
comment `owned-s21-t21:37ebcb10ed7f4528b7f34c846fed747b`,0062.
Run8dc16cd6-e80f-48f5-8bde-9189518c867b; existing accountA
cd9c4de7-e648-4104-8663-32658d33fee5, new accountB
fa18b1b5-cf95-487a-9127-f7290febf432, empty account
04e4f2b3-4662-44b0-aff6-558cda3c191f. PlansA99924d26-7720-47a4-aec8-563a6a237232
andB119d4c31-e97c-442e-960a-62d0d9620357. Original signed prerequisite and
financial records untouched. API14247/PID8468,8210; Vite19788,5210.
No finite tests running after25161 collection. No cloud/storage/provider calls.

New accountC receipt `/tmp/s21-five-views-coverage-20261003.json` is the original
seed snapshot. Actual jobdone, both sources enriched/current, coverage51 mapped.
No rerun of its empty-coverage precondition. C changes company totals; do not rerun
the original company360 oracle against that larger universe. Scope later
financial assertions to A/B explicitly. Coverage source is an explicitly seeded
release prerequisite, not signature/release acceptance proof.

Original seed is guarded against an existing receipt. Inspect its operations
and persisted versions before recovery; never blindly recreate grants/plans.
Original signed source was seeded in T21; this is not new signature proof.

## Commands

Safe read-only final check from `tests/e2e`, while the private runtime and grant
are valid (no need to rerun for status):
```sh
S21_VIEWS_COVERAGE_MANIFEST=/tmp/s21-five-views-coverage-20261003.json npx playwright test --config playwright.s21-local.config.ts s21-five-view-project-link.spec.ts --output test-results/s21-t18-demand-link-fixed --reporter=list
```
Historical25161 used `S21_VIEWS_MANIFEST=/tmp/s21-five-views-20261003.json`
and `s21-five-views.spec.ts --grep 'persisted five-view'` before accountC existed.
Do not rerun that company-total oracle on enlarged data. Coverage-controls needs
empty history;coverage-clear needsrevision51; both nowinvalid onrevision53.
Preserve receipts/history instead of silently rewriting fixture preconditions.
Do not rerun the already-passing empty/error case merely to obtain a green total.
The initial failure trace remains under
`tests/e2e/test-results/s21-t18-first/s21-five-views-T18-persist-dc880--scenario-with-exact-totals/trace.zip`.

## History

9231 lost-filter red ->78275 twelve UI green;27826 out-of-period red ->23542
25 UI green;68907 stale-month red ->41393 26 UI green.61327 test-only TypeScript
unsupported exact option ->76705 exit0. Worker53951 empty-name baseline3fail/
2pass ->21158 five green; integratedae753de. Fixture0062 prefix guard caught
before execution and corrected3067020->8eba150. Constructor parsing alone did
not catch incomplete economic inputs; add actual calculation completeness to
fixture validation to avoid repeating this class of failed run.
Controls70771 timed out on Playwright exact getByLabel for wrapped native
select before any saved revision. Role/name locator correction preserves the
literal accessible label;75122 focused unit passes (6 unselected),99259 real
browser passes. No production label change needed. Per-action timeout15s now
avoids waiting the whole180s for a missing control. No automatic retries.

Coverage93783 failed422 before a saved mapping: unknown skills/level cannot
identify a coverable demand. Actual UI enrichment fixed the test prerequisite;
31702 passes without weakening source validation. Sourcepaging62400 failed on
test locator: Versioned plans labels its enclosing region, not table. Literal
51-row and900 financial preconditions passed before locator failure.73574 uses
the correct labelled region and actual tab name; no application change/reseed.
73574 returned to a still-loading page; trace records3.3-4.1second local requests.
Explicit15second loading-completion wait (same action budget, no retry) in32834
passes all unchanged assertions; this is not performance acceptance.32834's
separate exact-interval check failed before writes because expected literals
omitted monthly boundaries.69292 corrected allfive/three intervals and passed
clear/restore before the wrong-route expectation. QA withdrew that assumption.
29263 reproduces the actual asynchronous anchor navigation defect independently.
4582/18745 anchor unit failed because the initial Element prototype spy was
shadowed by the shared HTMLElement polyfill; correct prototype spy79245 passes.
Browser29263 remains the valid red reproduction.13605 typecheck caught three
test-only Testing Library `exact` options; removed (string-name matching stays
exact),77526 passes. Do not copy Playwright-specific options into Testing Library.
