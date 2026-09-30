# S20 · contracts (Lead-owned, versioned; workers read first, patch via requests.md)

Version: v1 · 2026-09-30 05:05 UTC.

Every worker reads this file at spawn time. Anything ambiguous is resolved
against this document first, the review + directive second, the tests
third. Workers propose changes via `requests.md`; the Lead applies edits
here with a dated line at the bottom.

---

## §1 Status vocabulary (directive §3, review "Honest status language")

Every capability, every field, every worker output ends in exactly one of
these six states. Zero, none, approved, complete are reserved for
**verified** states.

| Term | When to use |
| --- | --- |
| `verified working` | Behavior matches contract; test proves it; evidence linked. |
| `fixed and tested` | Was broken; fix committed on `s20/W*`; regression + acceptance test proves it. |
| `missing` | Owner-owned action exists to build it; not tonight-blocked. Includes "honest placeholder" surfaces. |
| `blocked` | External dependency I named in the unresolved list. Never a synonym for "we didn't get to it". |
| `deferred` | Explicit product-owner decision to defer, with cross-reference. Not usable to hide missing work. |
| `Unknown` / `Not assessed` / `Not configured` / `Processing` / `Failed` / `Stale` | UI-level state labels (never map to a capability state, but any UI that renders one of these MUST also render the reason and next action). |

**Zero is never a stand-in for unknown.** GM unavailable → "Not assessed";
zero overdue actions → only if the query proved zero.

---

## §2 Fixed decisions (directive §1 — NOT choices)

| # | Decision | Enforcement |
| --- | --- | --- |
| D1 | Many SOWs per deal. Rollup headline = most-blocked open package by `changes requested > CEO exception > in review > awaiting signature > approved > draft`. Archived/superseded counted separately. Released never hides pending. | Owner: W3. Test: T14, T31. Model: verify `Sow.opportunity_id` uniqueness constraint before UI changes; if unique, the constraint must relax. |
| D2 | Three ownerships: deal sales owner (HubSpot owner id via owner mirror, archived included), client account owner (HubSpot company owner property, else "not set" — never derived from a deal), local assignee (DealGate user, tasks/actions only). Unresolved reference → "Owner details unavailable"; empty source → "Unassigned". | Owner: W1 (owner mirror), W2 (display), W6 (local assignee). Test: T04, T31. |
| D3 | NDA/MSA = two independent facts: **on file** (document uploaded ✓/–, file link, uploader, time; `on file ≠ signed/verified`) + **signed/verified** (only via existing SOW Legal review or an explicit verification record). Neither blocks review/submission. Remove NDA/MSA from Signature hold reasons unless an explicit verification requirement exists in code — if it does, record in `decisions.md`. | Owner: W3 (SOW), W2 (client detail display). Test: T15, T41. |
| D4 | Continuous consumer service (§4 cutover). Freshness = source-specific watermarks (received / processed / last reconcile), never a worker heartbeat. Public target "typically under 2 minutes", measured. | Owner: W1. Test: T32. |
| D5 | Deployment: scripted branch → staging path: **migration (backward-compatible) → api + all worker task-defs on one immutable image → smoke → SPA publish → invalidation → gates**. CI-on-main is post-merge only. `docs/runbooks/deploy.md`. | Owner: W4 (runbook), Lead (execution tonight). Test: T36. |
| D6 | Governed-record deletion: draft SOW with no submitted package → delete by authorized role + audit line; anything submitted/approved/executed → archive or supersede. Remove routine "Delete client" from mirrored client pages. | Owner: W3. Test: T29. |
| D7 | Dedupe key = HubSpot source event id (or documented composite) with DB uniqueness guard. Record + audit + outbox committed **atomically** before SQS ack. | Owner: W1. Test: T34. |
| D8 | Renewals: two calendar months before term end; month-end clamped; business timezone. | Owner: W4. Test: T25. |
| D9 | Stage aggregation by `(pipeline_id, stage_id)`. Labels for display only. Explicit unknown-stage bucket. Zero-count stages rendered. | Owner: W1 (aggregation), W2 (chip render). Test: T02, T40. |
| D10 | Business Unit: discover via HubSpot properties API (deals, then companies). Record internal name/type/options. Type-aware mirroring. Property not found → `blocked` with evidence. | Owner: W1. Test: T09, T26. |

---

## §3 Response envelope (shared across new endpoints)

Every new list endpoint follows this shape so W2/W4/W6 stay consistent:

```jsonc
{
  "items": [ /* row shape defined per endpoint */ ],
  "total": 187,                     // global total for the filter, not the page
  "page": 1,
  "page_size": 25,                  // ∈ {25, 50, 100}
  "meta": {
    "freshness": {                  // sync watermark for this dataset (D4)
      "source": "hubspot_mirror",   // or "local_workflow"
      "received_at": "2026-09-30T04:57:12Z",   // last event received
      "processed_at": "2026-09-30T04:57:15Z",  // last event handled to completion
      "reconciled_at": "2026-09-30T04:00:00Z", // last full reconcile
      "state": "verified working"   // status vocabulary §1
    },
    "unknown_bucket": 0,            // count of rows whose stage/BU/owner couldn't resolve
    "filters_echo": { /* full filter set as applied, echoing user's URL state */ }
  }
}
```

For freshness state:
- `verified working` when `processed_at` ≤ 2 min behind `received_at` and last error nil.
- `Stale` when the gap > 2 min (yellow banner in UI).
- `Failed` when the last worker run had a non-null error (red banner + reason).

---

## §4 Filter contract (shared across every list page + report — review §"Filter contract")

- **Fields:** search (client or deal name, prefix + contains), multi-select
  `deal_owner[]`, `stage[]`, `business_unit[]`, `pipeline`, `open_closed` ∈
  `open | closed_won | closed_lost | any`, `attention[]`, `sow_state[]`,
  `group`, `date_field` ∈ `created | close | last_activity | action_due |
  last_contacted`, `date_from`, `date_to`, `date_preset` ∈ `last7 | last30 |
  last90 | next7 | next30 | next90 | this_month | this_quarter | custom`,
  `missing[]` (fields the row is missing).
- **OR within a field, AND between fields.**
- **Timezone:** the app declares `America/Los_Angeles` as business
  timezone. Datetime bounds convert on the server; date-only fields do
  not shift. Zone label rendered next to the date filter.
- **URL state:** filters, sort, view, page, page_size live in the URL
  querystring. **Explicit URL > localStorage.** Back restores everything
  (filters, page, scroll). Clear filters resets coherently including
  page.
- **Aggregate contract (review §"Aggregate contract"):** one permission-
  aware base query serves rows, counts, chips, rollups, exports. Same
  snapshot + scope before pagination. Stage totals reconcile to the
  matching deal total (including unknown-stage bucket). Zero-count
  stages rendered. Deal counted once in global totals even if it has
  multiple company associations. A client count is never a deal count.

---

## §5 Watermark keys (D4 — W1 owns definition, others read)

Table `sync_status` gains one row per source. Watermark keys:

| Key | Meaning |
| --- | --- |
| `hubspot_backfill` | Last full deal-listing scan (scan generation). |
| `hubspot_webhook_received` | Last verified webhook accepted. |
| `hubspot_webhook_processed` | Last event fully handled + audit committed (D7). |
| `hubspot_reconcile` | Last nightly reconciliation completion. |
| `hubspot_owner_mirror` | Last owner API refresh (includes archived). |
| `hubspot_pipeline_mirror` | Last pipelines/stages metadata refresh. |
| `hubspot_property_business_unit` | Last property-definition refresh (D10). |
| `hubspot_dlq_oldest_age_seconds` | Oldest message in DLQ (0 if empty). |
| `hubspot_queue_backlog_seconds` | Oldest visible message in main queue. |

The freshness object in §3 pulls from these. **No heartbeat is a
watermark.** A worker that ran successfully but did no work does not
advance `processed_at`.

---

## §6 Ownership map (directive §2, verbatim)

| Area | Owner |
| --- | --- |
| `api/app/models/*`, `api/alembic/versions/*`, `api/app/routers/__init__.py`, `api/app/schemas/*` | **Lead** — workers submit model/migration changes as patches in `requests.md`; Lead applies them and assigns migration ids to avoid multi-head |
| `api/app/integrations/hubspot*`, `services/hubspot_sync*`, `hubspot_backfill*`, `hubspot_owners*`, `hubspot_properties*`, `worker/`, `infra-tf/modules/hubspot`, `infra-tf/modules/schedulers`, `sync_status*` | W1 |
| `services/hubspot_pipeline.py`, `routers/pipeline.py`, `web/src/pages/v2/pipeline*`, `client*`, `deal*` | W2 |
| `services/next_action*`, `deal_comment*`, `tracking_group*`, `saved_view*`, their routers, `web/src/components/tracking/*` | W6 |
| `services/sow_*`, `approvals*`, `deletion.py`, `web/src/pages/v2/sow-workspace*`, `sow-studio*`, `approvals*` | W3 |
| `services/signature*`, `handoff*`, `release*`, `project*`, `forecast*`, `actuals*`, `web/src/pages/v2/signature*`, `handoff*`, `projects*` | W7 |
| `routers/reports*`, `services/report*`, `renewal*`, `web/src/pages/v2/command*`, `reports*`, `renewals*`, `settings/integrations*`, `docs/runbooks/deploy.md` | W4 |
| `tests/**`, `scripts/**` (except deploy scripts owned by W4), `docs/reports/s20/matrix.md`, `tests.md` | W5 |

Anything not listed → first worker to need it requests via `requests.md`;
Lead assigns.

---

## §7 Migration policy (Lead owns numbering)

- Every worker who needs a schema change writes a `requests.md` block:
  > `# W3-2026-09-30-01 · sow.opportunity_id uniqueness relax`
  > Reason: D1 says many SOWs per deal.
  > Change: drop unique constraint `sow_opportunity_id_key`; add composite index `(opportunity_id, created_at)`.
  > Rollback: recreate the unique constraint after archiving all-but-one per deal.
- Lead applies each request as a **new alembic revision** off the last-
  landed `head`. No two workers ever touch the same migration file. The
  Lead-authored revision cites the requesting worker.
- **All migrations backward-compatible tonight** (D5). New columns
  nullable; new tables only add; no `DROP` of populated columns until
  a follow-up slice.
- Lead runs `alembic heads` after each landing to prevent multi-head.

---

## §8 Cross-cutting requirements (directive §3)

- Names, not identifiers, everywhere (T09). Targeted checks that known
  ids never appear as labels; do not reject legitimate numeric names,
  amounts, dates.
- Server enforces every state change (§0.5). A disabled button is not a
  control — the server rejects with 403 + explicit reason.
- Permissions identical across UI, API, aggregates, search, groups,
  exports, downloads (T27).
- Retries reconcile, never repeat. Context survives refresh / new tab /
  Back; unsaved-change warnings; specific recoverable errors.
- Fixtures synthetic + tagged; real mirror records read-only.
- No engineering copy on business screens (review §"Keep context").
  "Last synced", not "mirror last flushed".

---

## §9 Contract log

- **2026-09-30 05:05 UTC · v1** · Initial from directive v2 + review. — Lead.
