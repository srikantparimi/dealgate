# S20 · unresolved (Session-1 hand-back)

Session-1 stabilization complete. `integrate/s20` @ `59ba7bc` on origin.
Deploy proved on staging (rev 53 · s20-3e5be98c). Full unit suite green
(943 pass / 0 fail / 159 xfail). Rollback proven (T36).

## Hard blocks (permission / external / irreversible on real data)

| # | Blocker | Owner | One-sentence ask |
| --- | --- | --- | --- |
| U01 | Multi-role Cognito approvers absent → T27 (permission uniformity) + T44 (12-step full journey with role hand-offs) cannot verify role partitioning. | Kanna | **Approve me to create 5 Cognito users (`submitter+delivery+hr+finance+legal`, ceo already exists) via a follow-up TF slice in `infra-tf/modules/e2e-approvers/` and populate the `officeapp-dev-e2e-approvers` Secrets Manager JSON — should I proceed?** |

**Removed from the prior list:**
- ~~U02 HubSpot write scope~~ — by design per D-ISO-01; not a block, removed.
- ~~U03 session-token cap~~ — no longer a block for Session 1; Sessions 2–6 operate under the same cap and adapt.
- ~~U04 D5 deploy not run~~ — done tonight (see `deploy.md`).
- ~~U05 SOW alembic~~ — landed at `20260930_0044_s20_lead_d1_d4` (constraint drop done dynamically after first attempt failed on Postgres constraint-name mismatch).
- ~~U06 sync_status alembic~~ — landed in the same revision (8 watermark columns).
- ~~U07 test_delete_everywhere~~ — fixed (test now asserts D6 archive semantics).
- ~~U08 test_sow_upload_binding~~ — fixed (needs_pick_payload cleared on bound path).
- ~~U09 W5 cross-worker requests~~ — deferred to per-worker Session 2–6 pickups (W5-01 e2e_cleanup regex, W5-03 mirror endpoint, W5-04 export CSV).

## Deferred to Sessions 2–6 (per-scope, not blockers)

The per-worker cycles finish the "verified working on staging" work
their unit tests already covered locally. Each session runs against
the current staging deploy (rev 53), no additional D5 roll unless the
work touches image / migration / task-def env.

- **Session 2 (W1):** wire the continuous-consumer service (§4 cutover) + T32/T33/T34 injection tests on staging, W5-01 e2e_cleanup regex, W5-03 mirror endpoint.
- **Session 3 (W2):** T02 chip reconciliation, T35 pagination-vs-total, W5-04 export CSV, T01 sidebar-nav failure (whichever route the T01 spec pointed at that missed its heading).
- **Session 4 (W6):** T05 filter cross-cut, T16 next-action editability, groups + saved_views manual + shared visibility.
- **Session 5 (W4):** T25 renewal alert emission, T39 command-centre reconcile, T43 integrations honesty, T42 portfolio report labels + basis, hook up the `sync_status` watermarks the migration 0044 landed columns for.
- **Session 6 (W7):** T22 executed-doc verification, T23 three-event release, T24 baseline/forecast/actuals separation.

## Two known regressions to fix, non-deploy-blocking

- Playwright T01 sidebar navigation fails on 1 nav item on staging (heading text mismatch). Which nav item is diagnosable from the Playwright trace at `test-results/s20-t01-sidebar-navigation-a7009-item-lands-on-its-own-route-chromium/trace.zip`. Session 3 (W2) picks up.
- W5's t40 + t44 Playwright suites are all skipped — expected, they were seeded to unblock once W2/W3/W7 land the pages the specs point at.
