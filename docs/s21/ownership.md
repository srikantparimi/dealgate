# Ownership, Capacity and Dependency Plan

Current20:00 UTC: one light author for the next bounded T40 card-to-list workflow,
not broad feature lanes. `s21/approval-card-population` / sibling
`dealgate-s21-approval-card` at5a5c42c owns only approvals list service/route,
new test_s21_approval_card.py and lane report (contracts.md final section).
Lead owns UI, browser setup and integration; lead Watching33527 holds the sole
heavy slot.145MiBfree/~1382MiBcompressor and16GiBdiskfree do not justify a second
runtime. Prior condition/QA workers finished and are idle. Historical limits
below explain earlier reductions; no weekly quota inference.

17:36 UTC capacity recheck after user's explicit budget resets: historical worker
errors are not proof of present account capacity. Reuse ONE existing QA agent
for a bounded read-only source review in a new isolated tree at current HEAD;
do not spawn replacement identities or launch a second slot unless it actually
works. Host has357373free4KiBpages (~1396MiB),323397compressorpages, load44.88;
this permits one light author/reviewer, not another heavy runtime. Lead alone
runs full combined regression, owns all production/schema/deploy files. QA owns
only docs/s21/qa-extraction-review.md in s21/qa-extraction-review / sibling
dealgate-s21-qa-extraction-review; no test/install/DB/browser/cloud jobs. If the
same agent returns quota error again, stop attempts and retain lead-only mode.

Committed before workers or application changes. Integration branch `feat/s21-forecast`; lead is the only integrator, migration writer and deployer. Workers submit small tested commits, never merge another lane or edit main. All paths below are relative to the repository.

## Capacity Decision

15:28 UTC: lead only. Both active worker agents reported an account usage limit
near 13:21 UTC and stopped; their reported retry time is Oct8 23:27. This is
an observed account constraint, separate from earlier host memory/CPU limits.
Do not launch replacements to bypass it. Lead recovered their uncommitted work
in the original isolated branches, integrated 57f7269/ec69a2b, and independently
verified extraction safeguards and PostgreSQL races (81278e1). All worker trees
remain preserved. Lead owns subsequent production edits and integration; the
single heavy runtime is full backend regression 14168. No worker is running.
Resume two workers only after availability is established, with the existing
explicit ownership, isolated branches/runtime and one-heavy-runtime controls.

13:09 UTC: A active s21/extraction-overrides / dealgate-s21-extraction-overrides
at0dd0432, contract4f2d3ea: own sow_extract.py replay/merge helpers, sow.py
reextract gate/docstring, new test_s21_extraction_overrides.py and lane report.
Existing tests/assertions remain lead-owned. A's16new tests authored; runtime
held until lead61650browser ends. QA second lightworker in s21/qa-coverage-locks /
dealgate-s21-qa-coverage-locks at4f2d3ea owns only new guarded PGconcurrency
script and report. QA author-only, no DB/runtime; leadwillreview/run in a
self-created privateDB onownPGcontainer, neverreset retained/shareddatabases.
Lead owns coverage recovery1eff2e8, UIparent, integration, migrations/deploy.

12:57 UTC: D editor complete48c5cf4, integrated844a6a8; runtime released.
QA now owns focused test slot. A owns read-only extraction corpus audit in
dealgate-s21-extraction-corpus-audit / s21/extraction-corpus-audit at844a6a8,
ONLY docs/s21/lanes/extraction-corpus-audit.md; no tests/install/cloud/runtime.
Lead integratescoverage browser/PG and owns all follow-up production fixes.

12:49 UTC: second slot reserved for independent coverage QA, author/review only
until lead releases test slot. Own tree dealgate-s21-qa-coverage, branch
s21/qa-coverage at3d83bc9; exclusively new test_s21_coverage_independent.py and
docs/s21/qa-coverage.md. No production/schema/other tests/shared runtime edits.
Host12:47 has1144MiBunused/585MiBcompressor/29.67%idle and zero sampled swapIO;
memory recovered enough for bounded read/author work, despite54runnable and
load74.45. Therefore maxTWO lightweightworkers, stillONE heavy runtime. D owns
coverage-editor isolated tree/branch atd21eb08, new API/component/focusedtests/
lane report only. D finite tests currently occupy the slot; leadPG/browser wait.

12:31-12:38 UTC: one authoring worker retained because38then31runnable,
118then23MiBunused and compressor up2254MiB; no observed account throttle.
These measurements, not arbitrary agent count, caused the temporary reduction.
Lead owns coverage service/API/parent/migrations/deploy. API8210session84776 now
serves3d83bc9; own retainedDB0059 upgraded after private pre0059dump. No resets.

11:58 UTC refresh afterfullweb:6runnable,load12.58/26.12/44.00,31.73%idle,
162MiBunused/1023MiBcompressor,zero sampled swapIO. Permit two lightweight
authors again, not concurrent heavytests. Lead fullbackend owns heavy slot.
No account throttle observed or quota inferred.

11:26 UTC refresh: 28 runnable, load33.46/22.20/42.92,22.73%CPU idle,
30MiB unused and3399MiB compressor, zero sampled swap I/O. Keep ONE active
authoring worker for now (A retained-project scope); lead runs the connected
browser proof. Do not launch a second runtime or worker under this renewed
memory pressure. This is host capacity, not an observed account throttle.
Recheck after browser completion; two lightweight slots remain the ceiling,
not a requirement to occupy them regardless of pressure.

10:41 UTC refresh:20runnable,load33.23/52.44/58.62,17.3%idle,1607MiBunused,
1101MiBcompressor,zero sampled swapIO. Continue at most TWO lightweight authoring
workers, only ONE test-bearing slot. A currently owns that slot for facet tests;
lead authors sourcing contracts/schema. QA report-only has no runtime. No
observed account throttle; host pressure forbids two concurrent heavy suites.

10:38 UTC: two bounded workers at494ae2e. A in s21/crm-facet-wiring /
dealgate-s21-crm-facet-wiring owns pipeline.py facet endpoint/filter plumbing,
Pipeline.tsx facet request lifecycle, client.ts getPipelineFacets function ONLY,
new dedicated facet tests and own lane report. Author-only while lead browser
and regression occupy the heavy slot. QA in s21/qa-retained-demand /
dealgate-s21-qa-retained-demand owns ONLY docs/s21/qa-retained-demand.md,
read-only contract audit with no runtime. Lead retains canonical delivery
baseline repair, all migrations, integrations, PostgreSQL and deployment.

10:12 UTC current transfers: A worker s21/crm-bu-readers in its own new tree
owns hubspot_pipeline.py BU helper/filter/facet/projection blocks, one new test
and report. Independent QA s21/qa-company-demand owns one new Company X service
test/report only. Both author without runtime while lead full-backend regression
40329 runs at7f98459 against disposable s21_schema. Prior D demand UI workers
completedc1d92d0/d1936a7 and returned ownership; lead owns parent wiring, browser
proof and subsequent integration. No shared queue/DB/browser worker runtimes.

09:33 UTC host recheck confirms lightweight overlap remains reasonable:
6 runnable, load9.99/27.41/31.43,37.13% CPU idle,697MiB unused memory,
1002MiB compressor and zero sampled swap I/O. Two authoring workers remain
the maximum; no account-capacity limit has been observed or inferred. Binding
worker has released its slot after73passes, integrated2f76883; QA now runs
bounded projection tests. Lead publication tests await that runtime release.

09:31 UTC: use the two previously authorized lightweight slots for independent
work: governance worker on `s21/plan-staffing-binding` in
`dealgate-s21-plan-binding` owns only forecast_plans._bind, its new binding tests
and lane report; QA on `s21/qa-demand-publication` in `dealgate-s21-qa-demand`
owns only test_s21_demand_source_independent.py and its QA report. Lead owns
publication service/API/schema, integration and connected proof. Test runtime
remains serialized, initially assigned to binding worker. No second DB, queue,
browser or cloud runtime is shared or launched. Projection integrated eda7300.

08:50 UTC: permit TWO lightweight authoring workers after improvement to38.17%
CPU idle,301MiBunused/985MiBcompressor,22runnable,load12.75/18.75/39.12,zero
sampled swap I/O. This is not headroom for simultaneous heavy runtimes: lead PG,
worker unit suites and browser remain serialized. One D supply UI worker plus
independent import QA in separate trees; no parallel install or cloud jobs.

08:14 UTC: retain ONE lightweight worker. Host sample: 23 runnable,
load 12.38/22.70/28.98, CPU 20.35% idle, only 19 MiB unused physical memory,
3052 MiB compressor, zero sampled swap I/O. This does not establish current
swap thrashing or account throttling, but does not justify a second runtime.
QA authors independent People allocation tests while lead serializes PG/API/web
verification. Prior A/B/D workers are idle. Recheck before another worker launch.

07:49 UTC: host pressure renewed89runnable,load70.25/28.19/23.02,25.69%idle,
246MiBunused/1197MiBcompressor,zero sampled swap I/O;disk16GiBfree. Two workers
permitted only as ONE boundedtest-bearing QA plus ONE author-only D. No concurrent
installs/browser/fulltests. A/B priorincrements finished; no quota throttle seen.

07:19 UTC: full backend completed and host recovered to3runnable processes,
load7.59/13.94/21.89,40%CPUidle,828MiBunused,891MiBcompressor,zero sampled
swap I/O. Permit TWO bounded workers: A2 source adapter has the sole test slot;
independent QA in new `s21/qa-regression-gap` / `dealgate-s21-qa-regression-gap`
at922c4b9 owns ONLY docs/s21/qa-regression-gaps.md, read-only code inventory of
150inheritedxfails/oneopt-in skip versus meaningful coverage. No QA runtime,
cloud access or installs. Lead owns0055schema/scan protocol and integrations.
This measured overlap does not yet justify dividing effort by worker count.

06:10 UTC second sample: runnable processes9then4,CPUidle29then44.32%,1min
load8.86then8.39 (5min30.46,15min57.91still elevated), no sampled swap I/O.
Memory remains tight (32MiBunused,3.26GiBcompressor), so this is NOT permission
for two additional heavy test runtimes. Permit a bounded SECOND worker for
read-only CRM source/BU/owner integration inventory while QA finishes its own
SQLite cases. No node install/browser/database/cloud runtime for that slot.
Lead continues parent browser/DB preparation; heavy suites remain serialized.
Record productive overlap before changing the one-worker ETA assumption.

2026-10-02 05:54 UTC refresh after user authorized a second worker when capacity
permits: retain ONE for now. `top`:4logical CPUs,75runnable processes,1/5/15min
load55.40/62.92/93.82,25.60%CPUidle;16GiBphysical used,131MiBunused and1.37GiB
compressor. `memory_pressure` reports71%reclaimable/free pressure capacity and
zero throttled pages; this is not71%unusedphysicalRAM. Snapshot swap delta0,
but substantial cumulative swap is not treated as current thrashing proof.
Disk17GiBfree. Own PostgreSQL103MiB/512MiB,0.01%CPU; unrelated buildkit650MiB
untouched. Host CPU/load, not an invented account quota, prevents increasing
test-bearing worker concurrency now. No account throttling observed; actual
quota unavailable. Recheck at the next checkpoint/after heavy suites finish.
Independent A-source and D-view work exists; when measured headroom permits,
give a second worker its own explicit paths/tree/runtime, with only one heavy
browser/load suite at a time. The32-50h ETA assumes one worker and is unchanged.

2026-10-01: only lead active according to collaboration inventory; 16 GiB RAM, 4 logical CPUs, ~21 GiB disk free (90% used), substantial cumulative swap. Docker has an existing buildkit container owned by another workflow: leave it alone. Account token/concurrency quota is not exposed by available tooling. Therefore start ONE worker, not two; do not equate additional worktrees with capacity.

After the first bounded task completes, inspect throttling, resource pressure and runtime workload. Increase to two active workers only after recording evidence of headroom. Never exceed two. Run heavy browser/load suites serially. On throttling stop new launches and resume existing checkpoints rather than create replacements.

## File Ownership

12:02 UTC two author-only tasks at07c36b8: D in s21/demand-coverage /
dealgate-s21-demand-coverage owns newgm/demand_coverage.py,newtest_s21_demand_coverage.py
andownlanereport only. A in s21/smoke-service-binding /dealgate-s21-smoke-service-binding
owns deploy-smoke.sh Step2/modelbinding definitions only,newsmoke_model_binding.py,
newtest_s21_smoke_model_binding.py andownreport. Neither runs tests until lead
fullbackend86168 releases heavy slot; no cloud/DB/sharedruntime. Lead alone
owns sourceintegration, allschema/engine edits, cloudreadonlyevidence anddeploy.

11:38 UTC: scope worker0a54345 integrated6889915 and idle. Independent QA
in s21/qa-project-scope /dealgate-s21-qa-project-scope at6889915 owns ONLY
newtest_s21_project_scope_independent.py anddocs/s21/qa-project-scope.md.
Production read-only; author-only until lead fullweb77018 releases runtime.
Lead owns project publications/readers/allocation/sourcing/UI integration,
all migrations and connected proof. Only one authoring worker active.

09:11 UTC: after supplyUI6d46390 integrated5311afd, D moved to
`s21/demand-source-projection` / `dealgate-s21-demand-source` at0c8880b. Owns
ONLY newapp/gm/demand_source.py,newtest_s21_demand_source.py, ownlane report.
Pure cost-free projection of existing PricingComponent staffing, stable
component/assignment keys and explicit missingcapability/evidence. Lead owns
publication schema/service/worker/API/UI and all deployment. Author-only until
explicit slotgrant. QA workforce49c67f1 integrated4278726; QA nowidle.

08:52 UTC: D moves to `s21/people-supply-ui` / `dealgate-s21-people-ui` at70d7d2a,
owns ONLY new web/api/people.ts, pages/v2/PeoplePlanning.tsx,
__tests__/v2/PeoplePlanning.test.tsx and own lane report. Lead owns nav/App wiring,
API/schema and future demand/sourcing. Independent QA in`s21/qa-workforce-import`
/`dealgate-s21-qa-workforce` samebaseline owns ONLY newtest_s21_workforce_independent.py
anddocs/s21/qa-workforce.md; production read-only. Both initially author-only.
All runtime slots explicit; readonlyPython executable/currentPYTHONPATH/private
SQLite/no caches; D own copied node dependencies, no shared generated writes.

08:32-08:48 UTC: one worker D in `s21/plan-source-provenance` /
`dealgate-s21-plan-source`, base d44545b. Owns only forecast_plans.py
list_plans source provenance, then explicitly extended to outlook source URL
assembly; new test_s21_plan_source.py and own lanes/plan-source.md report.
117728d integrated8d9253f after32passes. Further stale/deleted/foreign link
tests are in progress with actual saved plan + calculation worker, not feature
mocks. Sole bounded test slot granted while lead authors People/API changes.
QA pure People worker finished367d11a integrated35bbe8d, no active runtime.
Lead retains schemas/migrations, People implementation, all integrations/deploy.

08:15 UTC: QA alone in `s21/qa-people-allocation` /
`dealgate-s21-qa-people`, base 2761da9, owns ONLY new
`api/tests/test_s21_people_independent.py` and `docs/s21/qa-people.md`.
Production and existing tests read-only. Author-only until lead grants a
serialized lightweight test slot; readonly dependency executable with local
PYTHONPATH, no bytecode/cache/shared runtime writes. Lead retains all integration,
People schema, source fixes and connected verification. D commits 6d35acc and
3bd7c08 integrated as ff8d10f and 351ed9b; that worker is idle.

07:53 UTC: QA in`s21/qa-scan`/`dealgate-s21-qa-scan`at1c5b245 owns ONLY
newtest_s21_scan_independent.py anddocs/s21/qa-scan.md; productionread-only,
privateSQLite/read-onlydependencyexecutable, nootherstate. Soleboundedtestslot.
D in`s21/next-opportunities`/`dealgate-s21-next-opportunities`ata5ef409 owns
Forecast.tsx,forecast/**,api/forecast.ts,newForecastOpportunities.test.tsx,
forecast_plans.py ONLYnewassumptioninput/service+additivelistfields,
routers/forecast.py ONLYnewassumptionsroute,newtest_s21_plan_assumptions.py,
ownnext-opportunitiesreport. Author-only untilruntimegrant. No sharedmodels,
nav/client/auth/deploy edits. Lead retainsPeople/schema/scanfixes/integration.

07:34 UTC: A2integrated4ecbd6d/83f8bc7 and sourceworker moved to
`s21/stage-qualified` / `dealgate-s21-stage-qualified` at83f8bc7. Own ONLY
services/hubspot_stage_mirror.py,newtest_s21_stage_qualified.py,ownlane report;
models/intake/oldtests read-only. Testslot afterleadPGproof. Secondboundedworker
B in `s21/renewal-calendar` / `dealgate-s21-renewal-calendar` at168b605 owns
signed_sow.py renewalhelper/imports only, stale renewal assertion/newrelease
renewalcases in test_signed_sow.py/newtest_s21_release_renewal.py,ownreport.
B author-only untilA releases slot. QA inventoryda4de2d integrated59e737c,
QA nowidle. Lead owns sourcecallerwiring, allschema/scanprotocol/PG/deployment.

07:09 UTC: sole implementation worker A in `s21/crm-metadata`, separate
`dealgate-s21-crm-metadata` at63ed085. Own services/hubspot_properties.py
(MODEL CLASS READ-ONLY), newtest_s21_metadata_availability.py and own lane
report only. Read-only prior dependency executable with explicit current-tree
PYTHONPATH/PYTHONDONTWRITEBYTECODE=1, private per-test SQLite, no cache/shared
writes. Bounded29-case slot then stop runtimes for lead fullsuite. Lead alone
owns schema/settings/routes/UI/deployment. No second test-bearing worker under
renewed host pressure; priorlight second-worker contracts integrated and idle.

06:42 UTC: Overview a72687d integrated2d9fc16. QA is sole test-bearing worker in
separate `s21/qa-overview` at2d9fc16, owns only new
ForecastOverviewIndependent.test.tsx and qa-overview.md. Its runtime is paused
until lead browser finishes: renewed host pressure06:38 shows116runnable,
load168/90/61,86MiBunused. Read-only D People contract67c9814 integratedeaaa61e;
second worker finished, no active runtime. Lead temporarily owns commercial
editor accessibility/layout/recovery corrections exposed by real browser checks.
No quota limitation asserted; other users' processes remain untouched.

06:27 UTC: TWO bounded workers after the documented CPU recovery. D worker
`s21/forecast-overview`, separate `dealgate-s21-forecast-overview` at6cd1e5a,
owns Forecast.tsx, forecast/**, new ForecastOverview.test.tsx and own lane
report only. Own node dependencies/process; no shared API/DB/browser/cloud.
Second A worker remains read-only for application code in its existing
`s21/crm-source-review` tree, refining only its own report into0054 contracts.
Lead owns parent QA corrections, schema and connected workflows. No two heavy
test runtimes; no additional workers. QA parent worker completed and idle.

06:10 UTC: second worker A in isolated`dealgate-s21-crm-source-review`, branch
`s21/crm-source-review` at9cf1e8a. Exclusive write
`docs/s21/lanes/crm-source-review.md`; all application files read-only. Deliver
exact metadata/owner adapter integration points,0054DDL proposal and concrete
regression cases, no provider calls or runtime setup. QA parent remains first
worker. Lead remains sole production/schema/integration writer for these paths.

05:57 UTC: independent commercial rerun is complete4bf6042; both commercial
workers idle. Sole next worker QA in new`dealgate-s21-qa-parent-cleanup`, branch
`s21/qa-parent-cleanup` at69ae2b0. Exclusive new tests
`api/tests/test_s21_parent_cleanup_independent.py` and report
`docs/s21/qa-parent-cleanup.md`; production read-only. Own SQLite fixtures/process,
no shared PostgreSQL/storage/cloud. Lead owns parent API/retry/UI and real0053
migration/retained-fixture proof. No second worker due recorded host pressure.

05:54 UTC: commercial fix08bceb2 integrated5ccabf6. Production worker idle.
Sole active worker independent QA rechecks its unchanged40-case suite in
`s21/qa-commercial-ui` at1815dbe (lead copied the fix). Only QA report/new
independent regression writes, no production edits. Lead owns parent0053 and
client/storage/API/UI changes. QA may not claim staging from boundary tests.

05:48 UTC: independent QA4057138 finished33pass7fail and is idle. Lead has
integrated its tests and copied that test commit into the existing clean
`s21/commercial-ui` worktree (a535458 plus QA). Commercial worker is again sole
active worker, same production paths and its own lane report; independent QA
test is READ-ONLY. Fix five reported defects without weakening assertions.
Lead retains parent deletion/schema and all runtime/deployment work.

05:39 UTC: commercial worker a535458 integrated as5b46289 and is idle. Sole
active worker is independent QA in `dealgate-s21-qa-commercial-ui`, branch
`s21/qa-commercial-ui` from5b46289. Exclusive writes: new
`web/src/__tests__/v2/CommercialEditorIndependent.test.tsx` and
`docs/s21/qa-commercial-ui.md`. Own node_modules/test process; no API, database,
browser, AWS or source changes. Lead owns summary regression correction, trusted
cleanup, all schema/integration and real browser proof. Do not share runtimes.

| Role | Exclusive implementation files | Next independent task |
| --- | --- | --- |
| Lead | CLAUDE.md, docs/s21 shared docs, scoreboard, api/app/models/**, api/alembic/**, api/app/main.py, api/app/db/**, web/src/App.tsx, web/src/api/client.ts, shared routing/nav/types, all dependency/CI files, infra-tf/**, deployment/runtime scripts | Finish baseline; fix approval containment and build real thin journey. Lead temporarily owns B and D until explicit transfer. |
| A CRM | services/{hubspot_pipeline,hubspot_intake,hubspot_backfill,tracking_group,next_action,deal_comment,watchlist,saved_view}.py; corresponding routers; worker/hubspot_*; web/src/pages/v2/{Pipeline,ClientDetail,DealDetail}.tsx and pipeline components | Exact-click filtered population/card membership and stale response regressions, then source metadata/chaos. No shared-file writes. |
| B SOW | services/{approval_routing,approval_workflow,signed_sow,handoff,delivery_acceptance,project_lifecycle,deletion}.py and SOW routers; web/src/pages/v2/{SowWorkspace,SowStudio}.tsx and sow-workspace/sow-studio components | Trusted approval provenance and reviewer preview; then deletion fences and full signature/delivery journey. State/schema changes proposed to lead. |
| C Commercial | api/app/gm/**; new api/tests/test_s21_calendar_schedule.py and test_s21_commercial_profiles.py; docs/s21/lanes/commercial.md | FIRST WORKER: calendar-derived monthly quantities and independently fixed oracle B regression; no DB/UI/worker edits. |
| D Forecast | services/forecast.py and new forecast projection/People services; forecast/actual/People routers; web/src/pages/v2 Forecast/People components and dedicated API module | Consume reviewed C schedules and canonical account scope; Company X read/write projection through all five views. |
| E QA | tests/e2e/specs/s21-forecast/**; tests/fixtures/sow/** and forecast/**; dedicated api/tests/s21_acceptance/**; docs/s21/qa/** | Independently derive A/B/C expected values and review C; then unskip/replace legacy t44 via explicit handoff of that file. Cannot approve its own fixes. |

Ownership only activates through a bounded task listing exact paths. Overlapping/unspecified existing tests, signatures, schema or shared client changes require lead transfer before editing. Shared files have ONE writer; no append-only multi-writer exception. A lane writes only its own handoff doc, not shared totals.

## Worktrees and Runtime

After contracts commit, first lane: `s21/commercial`, sibling `dealgate-s21-commercial`, explicit contract SHA. Later `s21/crm`, `s21/governance`, `s21/forecast`, `s21/qa` each fork reviewed integration SHA. Do not reuse S20 lanes. Lead cherry-picks each approved commit once and records SHA mapping.

| Runtime owner | Port reservation | State boundary |
| --- | --- | --- |
| Lead | API 8210, web 5210, DB 55421, object/queue emulator 45621 | s21_lead database, s21-lead object/queue namespace, .runtime local credentials/logs |
| First worker C | None needed for deterministic engine tests | Lane-owned venv, tmp_path fixtures; no cloud credentials, DB or queue consumer |
| Later worker / QA | Allocate and verify free ports before launch | Own database/storage/queue prefix/mail sink; NEVER copy shared .env or consume staging queues |

Runtime declarations are reservations, not proof services are running. Assert environment and run ownership before any destructive test. Unit in-memory SQLite tests do not replace actual migrated Postgres/storage/worker acceptance. Staging deploy has lead-only lock and requires release gate review plus any human Terraform approval.

S21F-01 checkpoint: C completed dcda0ace in its own branch/worktree and venv; lead integrated as e041387. Then independent QA completed 47c9c51 in its own branch/worktree/runtime; lead integrated as 0ffcb9b and alone fixed production as bd22cb7. QA independently rechecked all 13 tests on that exact commit. No two workers active simultaneously; capacity remains one. Lead-only Postgres runs in container dealgate-s21-lead-db on 127.0.0.1:55421 with 512 MiB/1 CPU limits. No other lane's runtime or dirty checkout touched. A/B/D implementation tasks remain scheduled, not complete.

## Waves and Estimate

05:12 UTC: deletion QA 5565273 integrated9a27f14 with six red cases; lead
fixed the unchanged assertions locally (24 combined pass). QA now idle.
ONE worker /root/s21_governance in dedicated `dealgate-s21-commercial-ui`,
branch `s21/commercial-ui` at9a27f14. Exclusive ownership: web/api/commercial.ts,
CommercialModelEditor.tsx and new sibling commercial-editor components,
CommercialModelEditor.test.tsx/newCommercialProfiles.test.tsx, own lane report.
Task: five remaining canonical pricing-profile editors. Own node_modules only;
no shared runtime/cloud/migrations/agents. Lead retains backend/deletion,
StaffingGmTab, shared client/App, tests/scripts, schema and operations.

04:20 UTC: independent actuals QA b86a725 integratedb859ead, lead fixesf944daa
pass unchanged QA plus real PostgreSQL revision race. All old workers idle.
ONE active worker /root/s21_crm_filters, separate dealgate-s21-crm-filters,
branchs21/crm-filters basedf944daa. Own services/hubspot_pipeline.py,
routers/pipeline.py, web/pages/v2/Pipeline.tsx, dedicated new population tests
and lane report only. No shared types/schema/nav/DB/cloud. Lead owns deletion
contracts/schema/services and actuals integration, full regression and operations.
Capacity remains one worker. Local API/web8210/5210; no staging deployment.

03:42 UTC: independent persistence QA finished bdb5f6c in new clean
dealgate-s21-qa-plans (branchs21/qa-plans), integrated65fa260; lead fixes ee4659c.
ONE active worker D frontend /root/s21_governance in dealgate-s21-forecast-ui,
branchs21/forecast-ui at65fa260. Owns new api/forecast.ts, Forecast.tsx,
forecast/** components, Forecast.test.tsx and own lane report only. Lead owns
App/nav integration, backend/source metadata, scripts/browser and all Terraform.
Other branches preserved idle; no cloud/DB runtime shared with worker.

03:21 UTC: B frontend3db1b93 integratedb991dc6; independent QAa7dab1e
integrated4af15f7; D forecastf2a88ed integrated1c5eca3. All workers idle.
Lead owns planning models/migration0050/services/routes/worker, signed commercial
guard, local browser proof. Next worker task will receive exact paths and SHA.
Capacity remains ONE worker; no shared cloud queue/database runtime.

S21F-02: C completed seven-profile source through 2862285; QA independently
added 2f7e494 with six failing financial cases. C now fixes those unchanged
tests on its own branch (sole active worker). Lead owns GM persistence/schema,
services/delivery_model.py integration and existing consumers, plus the local
browser proof under tests/e2e/local. QA owns its independent test file; no
production worker may edit it. Local API8210/web5210 now running on dedicated
s21_journey DB; no shared staging queue/mail or other lane runtime used.

02:56 UTC ownership update: C and QA finished bounded increments; B is the sole
active worker, `/root/s21_governance`, branch `s21/governance`, separate worktree
`dealgate-s21-governance` at2383d0b. Owns new CommercialModelEditor/api-commercial
module, StaffingGmTab, one new UI test and lane report; additive client.ts exports
only. No cloud/DB/browser runtime mutation. Lead owns all backend, Forecast pure
module/models/services/worker/schema and integrated real browser proof. C/QA
branches remain preserved and idle. Lead API8210 restarted; web5210 retained.

0. Verify S20 source/runtime/smoke, carryover and leak limitations; commit contracts and all 51 IDs / 45 scenarios.
1. Lead approval isolation + real vertical journey; one C worker implements tested calendar/schedule primitives. Integrate small reviewed changes immediately. Independent QA evaluates financial expectations before broader commercial consumption.
2. A CRM + B governance repairs and D Forecast/People follow within observed worker limit; lead assigns one-file ownership transfers. Build every pricing model, amendments, actuals and persisted planning/rules/imports.
3. Independent QA: complete regression, real faults and load, migration backup/restore, source parity, staging manifest/journeys/operational checks. Human canary, infrastructure prompt and mail recipient actions remain explicit dependencies.

Historical initial estimate:70-100 aggregate engineering hours, not elapsed time.
Superseded by [remaining estimate](remaining-estimate.md), assessed05:44UTC:
47-75 aggregate agent-hours /32-50 active elapsed hours to staging readiness,
with one worker plus lead, plus only non-overlapped external delay. See explicit
lane budgets, critical chain, uncertainty and post-approval main-image allowance.
