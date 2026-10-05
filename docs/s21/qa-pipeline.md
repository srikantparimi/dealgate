# Independent Pipeline Review

Session: 2026-10-02, bounded 15-minute QA increment, `s21/qa-pipeline`.
Reviewed source: `e73ca00d9832f9c5f5727ff9057b71e43eade2de`, including changes
`a771a37668967bfc5c5d266c79c83c3dc1f03aa9` and
`a3478c58b068f5c942cbff2d68b8f58bb47379c3`.
Only this report and `api/tests/test_s21_pipeline_independent.py` were added.
No production edits, existing-test weakening, migration, shared database,
cloud, browser, deployment, or additional agent was used.

## Findings

1. **P1: a later released sibling hides a still-pending SOW.**
   `api/app/services/hubspot_pipeline.py:1067` selects one newest package for the
   entire opportunity rather than current live state per SOW. An older pending
   Delivery/HR SOW and a newer released sibling return no opportunity under
   `attention=pending_approval`, despite an active review. An isolated read probe
   also observed unfiltered deal state `signed`, client state
   `in_review_delivery_hr`, and pending summary count 1 for that same deal.
   The existing `sow_rollup` contract explicitly says a released sibling must
   not hide pending work; these expectations are not taken from its output.

2. **P2: archived SOW history supplies current readiness and pending counts.**
   The package lookup at `hubspot_pipeline.py:1067` does not join the live SOW
   population. One live uploaded draft plus an archived pending Finance/Legal
   SOW disappears from `readiness=draft`. An isolated read probe observed both
   deal/client state `in_review_finance_legal` and pending count 1. The pending
   summary query at line 2078 likewise lacks the live-SOW restriction.

3. **P2: dynamic groups silently discard the pipeline predicate.**
   `api/app/routers/pipeline.py:476` reconstructs only a subset of saved filters.
   A group with pipeline `primary` and stage `qualified` also includes a deal
   with that stage ID in `other-pipeline`. Expected one member, observed two.
   Stage identity is pipeline-qualified by the integration contract. The CRM
   lane already reports the limited filter subset; this is an independent red
   reproduction of the remaining requirement, not a newly implemented fix.

4. **P2: client readiness reports no SOW for a matching uploaded draft.**
   `hubspot_pipeline.py:1788` invents SOW presence only when a package status
   exists. With one real stored SOW version and no approval package, the
   opportunity correctly reports `draft`, but its client reports `none`, even
   under `readiness=draft` with one matching deal.

5. **P2: client attention includes a deal excluded by the selected population.**
   `hubspot_pipeline.py:1642` calls `_client_closed_won_gap_subq()` without
   filters; the helper at line 1921 scans all same-client closed-won deals.
   Selecting owner A yields only A's open deal and matching count 1, yet the
   client gains `closed_won_not_released` from owner B's excluded closed deal.
   This is a filter-population discrepancy, not a demonstrated authorization leak.

6. **P2: stage-chip currency fabricates USD for an unknown source currency.**
   `hubspot_pipeline.py:1502` defaults NULL currency to `USD`. The same record
   is correctly `UNK: 1` in client and summary values, but `USD: 1` in the stage
   chip. Unknown currency must remain unresolved, not silently relabel money.

## Test Evidence

Used own existing Python 3.14 QA virtualenv executable with this worktree's
`PYTHONPATH=api`; all test data is in-memory SQLite. PostgreSQL migration hook
disabled explicitly. The new ASGI checks override authentication/session only;
they do not mock feature services or responses.

```sh
env -u DEALGATE_POSTGRES_URL PYTHONPATH=api \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest \
  api/tests/test_s21_pipeline_independent.py \
  api/tests/test_s21_pipeline_population.py -o addopts=-ra -q
```

Expected/collected/executed **27**; passed **21**; failed **6**; skipped **0**;
xfail **0**; not run **0**; exit 1, 18.85 seconds. New independent file: 18
cases, 12 passed / 6 failed. All nine existing population tests pass. Ruff
passes. All six red assertions were unchanged after their first failed run.

Failing node prefix: `api/tests/test_s21_pipeline_independent.py::`

```text
test_dynamic_group_preserves_pipeline_qualified_stage_identity
test_later_released_sibling_cannot_hide_pending_sow_attention
test_archived_sow_cannot_supply_current_readiness_or_pending_counts
test_client_readiness_agrees_with_its_single_matching_uploaded_draft
test_client_attention_excludes_closed_won_deal_outside_selected_owner
test_unknown_currency_is_not_relabelled_usd_in_stage_chip
```

Independent green coverage: readiness/attention select exactly 56 of 84 deals
across pages of 25/25/6/0, with stable out-of-range totals, exact client IDs and
matching counts, all-page stage counts and independently derived USD 2408 sum.
Zero matches stays zero; explicit no-match-client toggle restores only the
client population without inventing matching money. Group unions intersect
watching, client watches expand, duplicate memberships do not inflate totals,
and all 231 dynamic members survive (no first-200 cap). Watched amounts 2 + 231
produce 233. HTTP page zero is rejected; page 99 remains empty with total 1.

Trusted-fixture checks cover valid issuance, foreign tenant/environment, expiry,
CRM-mirrored deal and changed authoritative owner across opportunity/client/
summary populations. All pass without bypasses. Only the fixture clock is
advanced to test expiry; production feature functions remain real.

## Status And Limits

| Item | State | Evidence / remaining scope |
| --- | --- | --- |
| S21F:T09 | missing | Pagination controls pass; six semantic/population defects remain. |
| S21F:T31 | deferred | 231-row local correctness only; no representative 10k load, query-count or export timing proof. |
| S21F:T32 | deferred | Six fixture-scope cases pass locally; no full direct-API/export/deployed authorization acceptance. |

SOW/package statuses are explicit unit fixture setup, not upload/review/release
workflow acceptance. No browser chips, Back/reload, stale-response race, saved
view UI, full export, live HubSpot mapping, configured BU or staging proof is
claimed. The lead owns production fixes and integration verification.
