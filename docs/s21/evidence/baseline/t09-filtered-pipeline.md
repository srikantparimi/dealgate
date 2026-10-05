# T09 Filtered Pipeline: Passed Locally

Tested application508c450cf586c4284a8dd65ad23be9e95f78e7ef, committed unchanged
after proof. Browser62013 passes1/1.1m (test1.0m), no retries/skips.9 affected UI
cases69331 pass7.31s; typecheck39810 exits0. T09 closes locally, not staging or
live source parity. Broader parent requirements remain partial.
Lead owns Pipeline.tsx, additive api/client.ts download helper and focused UI
tests. Governance owns only the new dedicated synthetic fixture helper/report
in dealgate-s21-filter-fixture, s21/pipeline-filter-fixture, basebd188a3.
Contract and runtime boundaries committed e2963cd before fixture implementation.

## Current Evidence

- [Independent fixture manifest](t09-fixture.json):88 synthetic CRM deals,
  23 clients, positive configured BU, disjoint owner/stage/BU cohorts. Selected
  exact64 IDs across25+25+14 pages,16 matching clients,USD64000.
- Real browser/API/PostgreSQL0061: click filters/chip; exact ordered page IDs,
  stage count/value and client/API summaries; [downloaded64-row CSV](t09-selected.csv)
  from page3 contains every exact deal/amount and independent total.
- Reload/page3/Deal/Back preserves identity; remove BU retains owner/stage and
 72-deal totals/client membership. Saved stage-only view clears stale predicates,
  applies configured sort and survives reload with8 exact IDs.
- Zero result has0 deals,0 matching clients and empty money totals. Delayed
  genuine responses independently contain10 exact deals,3 clients4/4/2 and
  USD10000; after their successful completion the newer result remains exact0.
- Client-only display toggle does not contaminate CSV query or cause400.
- [Empty-result screenshot](t09-empty.png) inspected, not sole proof. Final
  artifacts: tests/e2e/test-results/s21-t09-saved-sort/.last-run.json and its
  two downloaded CSV files. Features were never mocked; only identity headers
  and release timing of genuine responses were controlled.

## Historical Repairs

- Saved-view application replaces old predicates while preserving page size.
  Red13153 retained old-owner; fix42043 passes7 affected UI cases.
- Pipeline now offers an authenticated active-filter CSV download, serializing
  the same filters as readers and removing page/page_size for all matches.
  Visible error state retains current filters.12197 had2 expected red tests.
- 98555:8pass/1fail because jsdom Blob lacks .text(), not a production failure.
  FileReader preserves the byte-content assertion;28086 all9 pass8.67s.
- Typecheck76779 exits0. No browser/private-DB proof yet.
- Lead integrated fixture8112e3f as4d1a1bf, migrated private0061/seeded88deals.
  First browser59297 failed12.9s before listing: real Watching-count query used
  page_size1, API requires25/50/100. Existing Watching-only proofs reused main
  rows and missed this ordinary-view path. Fix uses25, preserves exact total;
  unit expectation now enforces the real supported contract, not the bad size.
-41578 reaches64 selected deals after fix; fails harness tab name ('Clients
  (16)' vs actual 'Clients (16 matching)'). Correct only exact label.78802 active
  output s21-t09-client-label. Old traces retained, no retry/timeout changes.
-78802 passes all selected pages/export/navigation/removal, then finds saved
  sort_json ignored. QA finds show_clients_without_matches sent to CSV400 and
  stale-summary substring0 assertion also matching10.70723 reproduces2 UI red;
  saved-sort application/landing and export flag fixes69331 pass9/7.31s.
  Browser62013 passed s21-t09-saved-sort with exact stale0, held10deal/3client/
  USD10000 real payload verification and successful response completion. Also
  downloads zero-result CSV with client-only display toggle enabled.

Focused command from web:
`npx vitest run src/__tests__/v2/S21PipelineFacets.test.tsx src/__tests__/v2/S21PipelinePopulation.test.tsx`.
`npx tsc --noEmit`.

## Runtime And Cleanup

Lead migrated15454 and seeded4960 private DB
`s21_filter_850f3ce6dd7a4295b7dd296e2f1e8558`,OID89932,owner s21,
comment `owned-s21-t09:850f3ce6dd7a4295b7dd296e2f1e8558`, on owned55421.
API72859/PID60309 served this DB; no cloud/provider/queue/storage work.
Negative rerun98211 correctly refused nonempty business tables (88deals,
23clients,3users,8savedviews after builtins); no duplicate fixtures written.
Exact name/OID/owner/comment verified again; owned API stopped/collected143,
database dropped WITHOUT FORCE, subsequent pg_database count0. Manifest retained
only as evidence, not instructions to reconnect to a deleted database.
Retained s21_journey unchanged; API83118/PID63262 restored on8210 at508c450,
GET/me200. Vite5210 unchanged. Both workers idle; no finite jobs remain.

Browser command used from tests/e2e:
`env S21_FILTER_MANIFEST=/tmp/s21-filter-850f3ce6-manifest.json npx playwright test --config playwright.s21-local.config.ts s21-pipeline-filters.spec.ts --workers=1 --output=test-results/s21-t09-saved-sort`.
For a future run create/migrate a NEW owned private DB, seed with the guarded
helper, point a serial owned API to it, and supply its new manifest. Never reuse
the old manifest against retained data or silently reseed an occupied DB.

## Broader Remaining Work

Independent QA confirms224f7f7 already proves shared-filter API export and real
PostgreSQL1002-row/2002USD snapshot consistency (83 affected passes). Do not
repeat that broad proof merely to report status. Its browser export gap is now closed locally.

T09 literal assertions pass. Parent S21-09/11/DG-03 still need broader date,
multiselect, permissions/load/mobile/cross-application and combined staging proof.

The private fixture must never add invented CRM fields to issued sow_upload
grants; seed only an empty, explicitly named synthetic CRM scratch DB. Lead alone
creates/migrates/starts/cleans it. Retained s21_journey0061 remains untouched.
Serial private runtime proof and cleanup completed; retained API8210 restored.
Memory pressure prohibits concurrent heavy suites/servers. Future proofs must
ownership-check any serial replacement rather than add parallel runtimes.
