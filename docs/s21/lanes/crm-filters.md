# CRM Filter Lane

Scope: S21-09 / S21-11, T09, local evidence only. Sole worker in
`dealgate-s21-crm-filters`, branch `s21/crm-filters`; lead integrates/deploys.
Three-hour scoped override applies. No staging or infrastructure changes.

## Checkpoint 1

Independent SQLite fixture: 60 clients/deals, two disjoint owners and four
stages over three pages. Three tests failed before the fix: client rows included
unmatched clients; searching a deal name excluded its client and produced a
summary Cartesian product; unavailable BU filtering silently returned all rows.
The same three tests plus seven existing query-service tests now pass (10/10).

Fixes: client membership requires a matching deal when filters are active;
default filtered ordering starts with matching count. Client values and summary
queries explicitly join their client predicates. Unavailable BU/account-owner
filters fail closed. Service supports an explicit no-match-client override;
API/UI wiring follows separately.

Unmet: readiness/attention before paging, out-of-range totals, group/watch scopes,
all-page exports, URL races and per-user defaults, browser staging proof.
Positive BU parity is blocked by absent source-model columns, not merely empty
live values: neither Client nor Opportunity defines `hubspot_business_unit`,
and Client has no `hubspot_owner_id`. Lead owns any migration/adapter work.

## Checkpoint 2

Shared SQL now applies readiness and attention before paging and stage/summary
aggregation. Out-of-range pages retain the full selected count. Overdue actions,
pending packages and agreement counts are scoped to the selected deal population.
Backend local regression: 14 tests pass, including seven new population tests.
One attention and one overdue count regression failed before their fixes; the
new readiness test initially had an invalid fixture field, corrected before
asserting the resulting behavior (not claimed as an observed pre-fix failure).

Trusted fixture visibility uses existing `account_scope` / `user_allowed`.
Ordinary users cannot see issued fixtures; test users see only current valid
grants, and binding a fixture to a real CRM identity invalidates that grant.
Scope precedes list, count, summary and paging. The service has no tenant field
for ordinary HubSpot rows; this patch does not invent tenant isolation.

UI unit regression: both independently delayed-response and remove-one chip
tests failed before edits and now pass. Old responses are ignored, chips name
active filters, and URL navigation updates the selected view. TypeScript passes.
These mocked network unit tests are NOT acceptance or staging proof.

Still unmet: configured BU adapter, group/watch scope reconciliation, all-page
export, no-match toggle frontend wiring, per-user full defaults, T09 real browser
journey, representative load. Source adapter currently requests deal
`hubspot_owner_id` and resolves it through `_resolve_owner`; no BU property is
requested in `integrations/hubspot.py` or persisted by `hubspot_intake.py`.

## Checkpoint 3

Group + Watching now intersect across axes, while multiple members within an
axis remain a union. Watching a client expands to its deals. Dynamic group
membership uses the shared SQL predicate without a first-200 cap (231-member
regression observed 200 before fix, now exact 231). Groups retain existing
read permissions via `tracking_group.load_group`. Clients and summary endpoints
now resolve the same group/watch/client scope as Opportunities.

16 focused backend tests pass (9 new + 7 pre-existing). The group/watch test
also sends real HTTP through ASGI to all three endpoints against seeded SQLite
and asserts the exact deal ID, client ID and total of 1. Its initial fixture
missed the watchlist model import before metadata setup; that setup issue was
corrected, not reported as a product failure. Two frontend unit tests pass,
including the explicit no-match-client toggle. Shared API serialization for
that toggle is lead commit `67dcc09`, not duplicated in this worker branch.

Unresolved scope remains: all-page authorized export, full per-user filter
defaults and saved-view replace semantics, complete date validation and
representative load, configured BU mirror, real browser/staging T09. Dynamic
groups still parse only their existing supported filter subset. Ordinary
CRM rows do not have tenant fields. The fixture-scope helper revalidates test
grants individually (test-only query overhead); production users use one grant
ID query. No complete S21 requirement is claimed.

Historical BU evidence for lead adapter work: `docs/reports/s20/requests.md`
W2-2026-09-30-03 requests the absent mirror columns and configured property
binding; `t03-parity/venetian_60275608921/comparison.md` records property absence.
This worker made no new cloud metadata request, so historical absence is not
presented as a fresh live verification.

Final adjacent run: 16 passed, 12 inherited xfails in the S20 filter,
stage-reconciliation and report skeletons. Those xfails are unchanged and
provide no acceptance evidence. Final frontend typecheck passed.

## Independent QA Remediation

QA commit `287bb8f3ed946a03ce60a5f8c24fff88568d83fe` was read in its
separate worktree, not cherry-picked or edited. Its unchanged absolute-path
test file reproduced six failures / twelve passes against this worker's code.

The six fixes are scoped to the existing query service and Pipeline router:

- Preserve the pipeline predicate when resolving dynamic groups.
- Select newest non-voided package per live SOW, then the most-blocked deal
  headline using the established SOW rollup precedence. Released siblings no
  longer hide pending review.
- Exclude archived SOW and superseded package history from current readiness
  and pending package counts.
- Derive client draft presence from actual live SOWs, not package existence.
- Apply the selected population to client closed-won attention.
- Keep unknown currency `UNK` consistently in chips, clients and summary.

After fixes: **18 independent QA cases passed**, zero skipped/xfail; **16 owned
and existing query-service cases passed**, zero skipped/xfail. No assertion or
QA file was changed. Commands use `env -u DEALGATE_POSTGRES_URL`,
`PYTHONPATH=/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-filters/api` and
`--import-mode=importlib`; test data remains isolated SQLite. The independent
test path is `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-pipeline/api/tests/test_s21_pipeline_independent.py`.

No browser, staging, migration or deployment proof is added. Whole-requirement
status and the previously listed remaining work are unchanged. No other file
ownership was needed.

Adjacent rollup regression: 7 passed, 8 inherited skeleton xfails; unchanged
xfails are not acceptance evidence. Further mixed-state coverage is still
needed for pending attention alongside a higher-priority rejected sibling and
for signature evidence belonging to a different/archived package; those are
not exercised by these six QA regressions.
