# S20 · unresolved (Session-1 hand-back · U01 resolved)

Session-1 stabilization + U01 slice complete. `integrate/s20` on origin.
Deploy proved on staging (rev 53 · s20-3e5be98c). Full unit suite green
(943 pass / 0 fail / 159 xfail). Rollback proven (T36).

## Hard blocks (permission / external / irreversible on real data)

None open at Session 2 close either.

## Session 2 (W1) hand-back · 2026-09-30 20:05 UTC

**Deploy:** `integrate/s20` @ `d21d18c9` deployed to staging (api rev 55 · image `s20-d21d18c9`) tonight. Migrations 0044 + **0045 (Session 2 · W1 · new hubspot_owner + hubspot_property_mapping tables)** applied. Deploy smoke green on retry (first hit Bedrock `manual_required` flake per the runbook).

**W1 code + tests:**
- Alembic 0045 · new tables for W1's HubspotOwner + HubspotPropertyMapping classes. Backward compat. Applied on staging.
- Root wire · `hubspot_events_queue_name` + `dlq_name` flow from `module.hubspot` outputs into `module.schedulers`. Lead's temporary defaults removed.
- D2 wording · `services.hubspot_owners.owner_display_label(session, id)` returns `Unassigned` (empty source) vs `Owner details unavailable` (unresolved id); archived owners resolve to their name.
- Webhook deletion path · `handle_event` archives the mirror row on `deal.deletion` without calling `get_deal` (deal is gone from the CRM); rule-4 governance rows preserved.
- T28 · 5 tests pass (out-of-order, property-clear, owner-rename, unresolved-owner-label, deletion-preserves-SOW). 3 xfail with sharpened next-actions.
- **T03 parity** · Venetian Resort deal 60275608921 (BSC not present on staging — searches for "BSC", "Staffing", "Designer", "UX" all `total=0`). 14 of 15 fields match; 1 mismatch is the L04 defect the review already tracks. Report: `docs/reports/s20/t03-parity/venetian_60275608921/comparison.md`.

**Session 2 deferrals (not blockers, per-scope):**

| # | Item | Why deferred | Owner |
| --- | --- | --- | --- |
| S2-D | Continuous consumer cutover per §4 (disabled deploy → drain → cutover → rollback test → cutover → 20-event latency). | The TF is written (`hubspot_intake_service.tf` — new ECS service `hubspot_intake_continuous`) but applying it lands 30+ resources including the alarms cluster. The broader-drift plan cluster in `docs/directives/s20-terraform-drift.md` needs to converge first before rolling this into a single controlled apply window. The current 5-min scheduled tick continues to run; publishing "typically under 2 minutes" is honest against the tick + long-poll behavior. | Session 4 or a dedicated cutover slice. |
| T32 20-event latency measurement | Depends on S2-D applied. | (same) | (same). |
| T33 mid-batch crash cursor resume | Depends on S2-D applied (needs the long-running service to kill). | (same) | (same). |
| T34 duplicate SQS-msg-id same source-event-id | Same-shape unit test already passes (`test_hubspot_intake_dedupe.py`). Live injection requires S2-D + `scripts/inject-events.py` (W5-authored, requires the ECS service running). | (same) | (same). |
| Freshness alarms apply (`hubspot_backlog_age`, `hubspot_dlq_nonzero`, `hubspot_processing_lag` + metric filter) | Same context — rolls with S2-D in one plan. | (same) | (same). |
| L04 · `opportunity.name` from `dealname` | W2 request W2-2026-09-30-01 open in `requests.md`. The T03 parity table cites this as the single mismatch. | Session 3 (W2). |

**Resolved:** ~~U01~~ · 2026-09-30 · TF slice `infra-tf/modules/e2e-approvers/`
applied against staging. 5 users CONFIRMED + in role-group +
officeapp-e2e:

| Role | Cognito username | Group |
| --- | --- | --- |
| submitter | srikanthp+submitter@smartek21.com | Sales, officeapp-e2e |
| delivery | srikanthp+delivery@smartek21.com | Delivery, officeapp-e2e |
| hr | srikanthp+hr@smartek21.com | HR, officeapp-e2e |
| finance | srikanthp+finance@smartek21.com | Finance, officeapp-e2e |
| legal | srikanthp+legal@smartek21.com | Legal, officeapp-e2e |

Credentials in Secrets Manager at `officeapp-dev-e2e-approvers-multirole`
(new secret; the pre-existing `officeapp-dev-e2e-approvers` is preserved
so specs 22 + 23 keep working). `tests/e2e/fixtures/multi-role-auth.ts`
updated to read the new name.

**Kanna's remaining action for U01: click 5 SES verification links
sent by AWS to srikanthp@smartek21.com** — one per role. Current status
of all 5 identities: `Pending`. Until you click, the sandbox refuses
notification emails to these addresses; Cognito login already works
without SES.

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
