# T11 Connected Tracking

## Current State

2026-10-02 22:25 UTC: **T11 passed locally**. Browser43442 passes1/44.9s,
all6 original conditions, with unchanged application files committed
1441649e4a571f2212cc20794cd32d87e7dd50af. UI23460 passes7; tsc69673 exits0.
Focused independent PG rerun69943 exits0 and persists exact lock/role evidence in
[t11-pg-races.log](t11-pg-races.log). This rerun was solely to retain the proof:
inline Playwright attachments are not persisted by the configured list reporter.
The test now writes its JSON attachment to disk for future runs; that artifact-only
addition was not part of43442. No assertions/application behavior changed after it.
Independent QA statically confirms both route repairs and literal condition mapping.
S21-13 remains Partial: unpin/full CRM endpoint/availability integration and staging
are broader than literal T11. No whole-requirement completion claim.

Implemented: Deal comment add/edit/pin/delete and action create/edit/complete;
registered authorized assignees; escaped CRM notes with author/time/source;
row revisions and conflict recovery; consistent Pipeline deal/fixture access;
edited activity attribution; route-generation fencing after mutations.
UI2c0b220, backendead07d9->5710f20, legacy fixf969d6b->6cb815b,
route guard/browser/PG scriptsd3f413e. No migrations.

Focused proof: UI43857 passes5, tsc66963 exits0. QA route race95689 red,
generation guard46511 passes6. Worker1819 passes30 (13 new +17 inherited).
No staging, Cognito, live CRM-note ingestion, cloud or notification claims.

## Connected Assertions

`tests/e2e/local/s21-tracking.spec.ts`: real issued fixture, registered peer,
declared synthetic CRM note via guarded scripts/s21_tracking_note_fixture.py;
create/edit/pin comment; create/edit/complete action; reload exact state and
newest activity type/actor/order; CRM note read-only409/escaping/attribution;
genuine concurrent API update while editor open, stale draft409 retains text.

`scripts/s21_tracking_pg.py`: same issued fixture, real ASGI/PG with declared
local role adapter. Two independent HTTP sessions wait on an observed row lock;
record pg_stat_activity PIDs/blockers before release. Pin vs edit and complete vs
title yield one200/one409, winner persists, exactly one mutation audit and one
action event. Sales allowed own edit, denied other author's edit with unchanged
value/audit; HR allowed cross-author edit. Executed inside43442 and durable69943.
Literal pairs selected by winning request index prove the losing field stays
unchanged. Durable comment waiters7043/7044 block behind7041/7043; action
waiters7042/7044 behind7041/7042. Each result200/409, mutation audit delta1.

Exact command from tests/e2e:
`npx playwright test --config playwright.s21-local.config.ts s21-tracking.spec.ts --workers=1 --output=test-results/s21-t11-connected`.
43442 and69943 are collected; no finite jobs from them remain. Each browser run issues fresh local fixtures; no
retained database reset, provider, queue or storage operations. Fixtures remain
under their expiring issued grants; no cleanup claim.

## History

- UI49378:2red missing controls;80226:2green, then43857:5green.
- tsc97285 failed obsolete unused facets and missing mocked facet email; narrow
  removal/fixture fix66963 green.
- Worker64031:9 failures with partially authored services/baseline routers (not
  pristine baseline red);42007 intermediate CRM readonly error-order failure;
  36816:13green. Legacy57137:9fail/8pass from required revisions and genuine
  second-precision latest ordering; preciseUTC create timestamps and actual
  revision setup preserve assertions,1819:30green.
- QA static route-refresh finding reproduced95689, repaired46511:6green.
- Initial restart readiness curl raced startup and exited7; API subsequently
  logged startup complete before browser assertions. No test retry configured.
- QA second route schedule: old mutation response finishes after navigation,
  then starts stale refresh.2007 red; capture originating render generation
  before mutation and check at refresh entry,23460 passes7.
- Browser79391 failed after note409/comment creation: nested textarea label lost
  exact accessible name for prefilled edit. Explicit label/id repair passed43442.
- QA improved PG oracle: winning request index determines literal unchanged loser
  field plus expected winner value; not comparison only to server response.

## Runtime

API8210/session49013/PID71287 atd3f413e, retained s21_journey0061 on owned
Docker55421. Previous83118/PID63262 ownership-checked stopped/collected143.
Vite5210/session19788 HMR. Browser43442 and PG69943 finished. Lead affected
backend15623 passes30 on integrated1441649; no finite tests remain. Fixture retained:
deal e1f219a2-580d-41c7-a575-643421782a01, grant expiry2026-10-03T02:18:54Z.
All writes are synthetic local tracking rows; no storage/queue/provider operation.
