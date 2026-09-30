# S20 · progress log for W6 (owned by W6 · continued by Session 4)

**Budget spent this session:** ~75 min wall clock / ~7.8k tokens output
(rule 16 hard-stop). Deploy landed on staging rev 60 (image
`s20-19301a4f`) with 33 impacted-suite pytests green, S20 Playwright
13 passed / 13 skipped (T40 L06b flaked once, passed cleanly on
retry).

## Cycle 4 · Session 4 · 2026-09-30 23:20 UTC

### Session state per directive item (rule 16 · five-state)

| # | Item | State on rev 60 | Proof |
| --- | --- | --- | --- |
| 1 | Next actions — description, owner, due, status; deal-page slot; completion writes audit; overdue attention flag; sort to top | **`fixed and tested (staging shape)`** | Model + router + service already landed pre-S4 (30 tests pass); DealDetail renders next-action list via `listNextActions`; `_derive_attention` flags `overdue_action` when `next_action_min_due < today`; DEFAULT_SORT_OPPS puts `next_action_due` asc so overdue rows lead. **Missing on staging proof:** user-picker + inline row edit UI not built this session — the slot renders read-only. Assignee-set audit exists in `next_action_event`; sort-to-top is verified by the query but not by a Playwright assertion this cycle. |
| 2 | Comments — scope, author, pinned, latest preview, role visibility, never to HubSpot | **`fixed and tested (staging shape)`** | Backend + `deal_comments` router + `deal_comment` service already landed pre-S4; `DealDetail` fetches latest via `listDealComments`. **Session 4 added item-9 role guard** (see item 9). Pipeline row "latest comment preview" (author · date) is **not surfaced** — server has the data (`latest_visible_comment`) but the OpportunityRow envelope doesn't ship it. Pinned-wins-over-newer semantics not yet asserted by a spec. HubSpot write-back: service does no `hubspot.update` — verified by grep. |
| 3 | Combined timeline on deal + client pages | **`verified working (staging)`** | New `/deals/{id}/timeline` + `/clients/{id}/timeline` router unions comments + next-action events + approval status transitions + SOW versions, sorted by ts, each entry labeled by source and rendered as a prose sentence. DealDetail + ClientDetail render the timeline block. Endpoint returns 401 for anon, 200 for authorised — verified. |
| 4 | Manual groups — CRUD, client/deal member, group filter in W2 filter bar, picker | **`fixed and tested (staging)`** for the filter axis + group listing; **`missing`** for the pinned-tabs picker | Backend (models + router + service + 30 pretests) already landed pre-S4. This session added the Group `<select>` on Pipeline FilterBar backed by `listTrackingGroups({member_kind:"opportunity"})`; URL-state `?group=<uuid>` scopes the list via `_resolve_scope` in the pipeline router. **Pinned-tabs picker** (up to 5 pinned tabs above the select) is not built — a single `<select>` renders. Auto-include-current-and-future for client groups is a server-side flag (`include_future_deals`) but there's no UI toggle. |
| 5 | Rule-based groups — filter_json evaluated by same engine, "why is this here" | **`fixed and tested (unit)`** | `_resolve_scope` in `api/app/routers/pipeline.py` evaluates a group's `filter_json` by calling `list_opportunities` with the JSON payload as a `PipelineFilters`. Test `test_rule_based_group_uses_same_query_engine` proves it. **"Why is this here"** predicate reveal on the row is **`missing`** — no UI element renders the matched predicates yet. Stage-change membership recomputes because the evaluation is on-the-fly per request; not asserted by a spec. |
| 6 | Saved views — filter-bar state saved by name, remembered last view; URL wins | **`fixed and tested (staging shape)`**; **`missing`** for last-view-remembered persistence | Backend router + service + 7 built-in views already landed. This session added a `<select>` "View" in FilterBar that merges the view's `filter_json` onto the URL via `commitFilters` (URL still wins because subsequent explicit URL entries just replace those keys). **Last-view remembered:** no localStorage/user-preference persistence added yet. |
| 7 | Watchlist — per-user star, "Watching" filter, Command center count | **`verified working (staging)`** | New: `WatchedItem` model + migration `20260930_0047_w6_watch` applied on staging Postgres. `/watchlist` GET/POST/DELETE. Pipeline router accepts `?watching=true` → resolves to caller's `WatchedItem.item_id` set. New `<WatchStar>` component wired on DealDetail + ClientDetail. FilterBar has a "Watching (N)" checkbox with count. **Command center Watching count metric** is **not added** — the count is only visible in the FilterBar label today. |
| 8 | Dashboards sum deals, not memberships | **`fixed and tested (unit)`** | `test_deal_in_multiple_groups_counts_once` seeds one deal in three groups; scoped list returns `total=1`. `list_opportunities.total` uses `func.count().over()` on the base opportunity set — membership joins never multiply the row. |
| 9 | Permissions test: viewer sees no comments, 403 on write | **`verified working (staging)`** | `deal_comments` router now uses `_require_comment_writer` (leader/sales/presales); GET returns `{items: [], latest: null}` for non-readers rather than 403 so the deal page doesn't blank. Unit test `test_comment_viewer_gets_empty_list_and_403_on_write` proves both branches. On staging, `GET /api/watchlist` and comment endpoints return 401 unauthenticated. |

### Files touched (Session 4)

**Backend (new):**
- `api/app/models/watchlist.py` — `WatchedItem`.
- `api/alembic/versions/20260930_0047_w6_watch.py` — creates `watched_item`.
- `api/app/routers/watchlist.py` — GET list, POST add, DELETE remove.
- `api/app/routers/timeline.py` — `/deals/{id}/timeline`, `/clients/{id}/timeline`.
- `api/tests/test_s20_w6_tracking.py` — 7 W6-integration tests.

**Backend (modified):**
- `api/app/services/hubspot_pipeline.py` — `PipelineFilters` gains `group`, `opportunity_id`, `watching_ids`; `_base_opportunity_filter` handles `opportunity_id` scope.
- `api/app/routers/pipeline.py` — new `_resolve_scope` helper; `list_opportunities_endpoint` accepts `group[]`, `watching=true`.
- `api/app/routers/deal_comments.py` — role guards on POST / PATCH / DELETE; empty list for non-readers on GET.
- `api/app/main.py` — registers `watchlist.router` + `timeline.router`.

**Frontend (new):**
- `web/src/ui-v2/WatchStar.tsx` — shared star toggle.

**Frontend (modified):**
- `web/src/api/client.ts` — TS types + client fns for tracking groups, saved views, watchlist, timeline; `PipelineFilters` TS gains `group` + `watching`.
- `web/src/pages/v2/Pipeline.tsx` — FilterBar adds Group + Saved-view + Watching selects; URL-state hooks read/write those params; `useEffect` fetches facets + groups + saved views + watchlist on mount.
- `web/src/pages/v2/DealDetail.tsx` — `<WatchStar>` in the header; combined timeline section.
- `web/src/pages/v2/ClientDetail.tsx` — `<WatchStar>` in the header; timeline replaces raw-JSON activity when non-empty.

### Proven

- 33 impacted pytests pass + 1 known xfail (`worker_crash_resumes_from_cursor`, W1 Session 4 scope).
- Playwright S20 on staging rev 60: 13 passed / 13 skipped (T44 + T01b remain deferred).
- Smoke green (single-truth gate green after the C8 fix in commit `19301a4f`; migration exit 0; cleanup gate 0 leaked clients).
- Endpoint routes registered + auth-gated (`/api/watchlist`, `/api/deals/{id}/timeline` both 401 unauthenticated).

### Next (Session 5 handoff)

Remaining deferrals to name here so Session 5 doesn't have to re-discover them:

- **Item 1**: user-picker + inline row edit + overdue-sort assertion. The audit event, the flag, and the sort are wired; the *UI editor* on the row and the *Playwright assertion on sort-to-top* remain.
- **Item 2**: latest-comment preview on the Pipeline `OpportunityRow` (server column); pinned-wins spec.
- **Item 4**: pinned-tabs picker above the Group select; include-future-deals toggle UI.
- **Item 5**: "why is this here" predicate reveal on the row.
- **Item 6**: last-view remembered per user (persist to localStorage or `user_preference` table).
- **Item 7**: Command center "Watching" count metric card.

### Blockers

None. Session 4 hit the 75-min wall clock at ~7,800 tokens output.
No merge to main.
