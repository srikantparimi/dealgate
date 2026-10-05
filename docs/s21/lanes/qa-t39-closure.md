# Independent T39 Closure Review

2026-10-02, bounded approximately 10-minute static review. Reviewed source
commits `9f23cb4fd02a3e0ba17fa3e8325246ed68d8dadf` and
`941953ab65d3621224906a5bdbe554fd09daa9aa`, plus the committed browser spec and
evidence report in the read-only integration tree at
`39f157505c2904dd8e75a86c5f8d3b0e4eb8cc0b`. No tests, application imports,
browser, database, provider or installation was run by this review. Only this
report was added to `s21/ocr-evidence`; the paused OCR checkpoint remains intact.
Line references are to the reviewed integration source, not this older QA tree.

## Findings Outside The Recorded T39 Happy Path

### 1. P2: Manual client groups lose authorized local watched deals

`api/app/routers/pipeline.py:506-508` expands manual client-group membership
through `matching_opportunity_ids` with an unscoped `PipelineFilters`. The
source predicate therefore accepts only HubSpot rows. By contrast, the new
watched-client expansion at `:524-528` first obtains trusted fixture scope.
The later group/watch intersection at `:530-535` cannot recover an ID already
dropped from the group population. Final scoped authorization is not the issue.

Concrete reproduction to add: issue a valid local fixture, create an owned
manual tracking group with `member_kind="client"` containing its exact client,
and watch either its exact opportunity or its client. The plain Watching list
and `/watchlist.matching_deal_count` include its one authorized deal. Adding
`group=<client-group-id>` returns no opportunities because the local deal never
entered `opp_scope`. Expected: the exact same one deal. Include another actor's
fixture as a negative control so fixing the source predicate cannot widen scope.

This is a residual source/filter correctness defect, not a newly identified
authorization leak. The recorded browser creates three **opportunity** groups
(`tests/e2e/local/s21-watching.spec.ts:44-53`) and therefore does not exercise
the client-group path. The original T39 fixture still passes as recorded;
CO-03's current-filter/group behavior remains broader.

### 2. P2: Pipeline Watching count does not honor current business filters

`api/app/routers/watchlist.py:79-82` always computes `matching_deal_count` using
default open-only `PipelineFilters()`, with no current Pipeline query inputs.
`web/src/pages/v2/Pipeline.tsx:333-370` fetches this count once independently of
the active query, then passes it to the `Watching (n)` label at `:605-606` and
`:1106`. The actual opportunities query uses the current filters at `:384-387`.

Concrete reproduction to add: watch one authorized open deal, then apply a
search/owner filter excluding it while Watching is enabled. The result set is
empty, but the Watching label remains 1. Alternatively, watch one authorized
closed deal and enable `include_closed=true`: the list contains that deal while
the label remains 0. This does not inflate the underlying authorized list or
leak another viewer's records, but it does not meet CO-03's instruction to
respect current filters (`docs/directives/s21-forecast-implementation.md:641`).

The global Command Center card has no selected Pipeline business filters and
correctly links to the default-open Watching population. That passing path is
not contradicted. If the Pipeline label is intentionally a global open-watch
count rather than a current-match count, its semantics must be made explicit;
the present label and shared `matching_deal_count` name do not distinguish them.
The T39 browser varies group membership, but does not vary business or closed
filters. This is a broader CO-03 reconciliation gap, not a claim that its
recorded 0 -> 1 -> 0 run failed.

## T39 Assertion Crosswalk

The original unchanged scenario is at `acceptance.md` T39 and directive
lines679-680. Its five explicit conditions have meaningful assertions in the
recorded local spec, not just test-name or paginator evidence:

| Condition | Actual assertions in s21-watching.spec.ts | Assessment |
| --- | --- | --- |
| Empty Watching card0 and empty destination | Lines36-43 assert API count0, visible card0, destination Opportunities(0), exact empty API items. | Covered locally. |
| One watched deal in three groups counts once | Lines44-61 create three persisted groups with exact member identity; lines69-73 assert combined group/watch total1 and exact deal ID. | Covered locally for opportunity groups. |
| Card and list contain the same deal, not just a number | Lines66-81 assert exact API singleton, card1, exact visible deal row, total row count1 and absent hidden row. | Covered locally. |
| Unwatch returns both surfaces to0 | Lines83-93 unstar in browser, verify persisted API count0/exact empty set, card0 and no destination deal rows. | Covered locally. |
| Viewer access is respected | Lines62-65 refuse another actor's fixture watch/detail with404; lines68/73/81 exclude its exact identity. | Covered locally for the tested cross-fixture boundary. |

The hook at lines11-13 only adds local identity headers using `route.continue`;
it does not fulfill/mock feature API responses. Local identity is explicitly
not Cognito. Fixture/group setup uses actual application endpoints. The browser
clicks the deal star and navigates the Command Center/destination, so this is
more than a service-only simulation.

Recorded evidence: `docs/s21/evidence/baseline/t39-watching.md:3-11` attributes
session46207 to application941953a with **1 passed (1.3m)**. The inspected local
`tests/e2e/test-results/s21-t39-941953a/.last-run.json` contains
`{"status":"passed","failedTests":[]}`. Runner config has `retries:0`;
the unchanged spec uses a120-second total test timeout, not a widened assertion
timeout. The prior failing readiness run remains explicitly disclosed. The
retained last-run JSON does not itself encode source revision or full assertions;
revision/environment attribution comes from the committed execution report.
Raw passing console output was not retained, as the report honestly states.

## Authorization Review

No concrete new grant bypass was found in the bounded changed paths:

- GET/POST require Pipeline reader authority; GET restricts watched rows to the
  current user, then removes inaccessible subjects before identities/counts are
  returned (`watchlist.py:64-86`). POST checks the same subject visibility before
  insert (`:96-100`). DELETE only removes the caller's own matching row, so its
  lack of a new reader check does not expose another user's state.
- The participant-list optimization is only a candidate filter
  (`hubspot_pipeline.py:578-605`). Every candidate still passes the latest
  `account_scope` query and owner/issuer/environment/tenant/expiry checks; an old
  membership alone does not grant access. Ordinary readers still hide all
  grant-bearing fixture clients. Exact fixture opportunity IDs remain scoped.
- Distinct Python ID sets union direct watches with expanded client watches;
  group multiplicity does not enter the `/watchlist` count. The focused test
  also checks client+deal double-watch deduplication and a pre-existing hidden
  watch row, which complements the browser's refused-add case.

Useful targeted follow-up, not an established defect: add an old grant naming
the viewer followed by a latest grant removing them, and assert no watch/list
identity or count survives. The new instrumentation test proves unrelated
grants avoid revalidation, but does not itself exercise that supersession case.

## Conclusion

The evidence supports the narrowly stated **T39 passed locally** classification;
this review does not independently execute or promote it to staging. The two
static CO-03 filter findings above need targeted reproduction and correction or
an explicit count-semantics decision. They should remain visible rather than
being hidden by the happy-path pass. They do not establish an authorization
regression or justify changing successful T39 assertions.

Screenshots are supplementary: the evidence report explicitly discloses its
below-viewport row, transient empty loading capture and unrelated summary error.
The test removes its watch and archives its groups, while issued fixture rows
remain intentionally under expiry/provenance controls. No whole Command Center,
S21-09/S21-14/DG-01/CO-03, staging, PO or release closure is claimed here.
