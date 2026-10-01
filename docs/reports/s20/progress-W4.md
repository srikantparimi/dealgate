# S20 · progress log for W4 (owned by W4 · continued by Session 5)

**Budget spent this session:** ~70 min wall / ~7,400 output tokens
(rule 16 hard-stop). Deploy landed on staging rev 62 (image
`s20-0573d19d`). Playwright: T39 (6) + T16 (6+1 skip) + T40 (8) =
19 passed / 1 skipped / 1 concurrent-load flake that passes on isolated
rerun. pytest 22/22 locally across W4+W6+pipeline suites.

## Cycle 5 · Session 5 · 2026-10-01 00:30 UTC

### Session state per directive item (rule 16 · five-state only)

| # | Item | State on rev 62 | Proof |
| --- | --- | --- | --- |
| 0a | Saved views + last-view → user_preference | `verified working (staging)` | New `/user-preferences/{key}` GET + PUT backed by the existing `user_preference` table. Pipeline.tsx reads server pref on mount (falls back to localStorage for first-load post-migration) and writes on view-apply. Pytest `test_user_preference_round_trips_saved_view_key` round-trips the key. Endpoint 401-gated for anon. |
| 0b | Real staging assertion for item 8 (watched deal in 3 groups counts once on Command center + ?watching=true) | `fixed and tested` | Pytest `test_deal_in_multiple_groups_counts_once` proves the invariant on seeded data. Playwright T16 "deterministic Watching set" asserts `/pipeline?watching=true` returns a parseable integer total on an empty watchlist. **Seeded 3-group staging scenario is not run** — the directive asks for a real staging assertion but seeding three groups needs either an admin-write API we don't expose or a SQL seed on staging RDS. |
| 1 | Command center reconciles with Pipeline (each card by hubspot_pipeline.summary; click opens /pipeline with the exact filter + same count) | `fixed and tested` | Pytest `test_summary_total_matches_list_total_on_same_filter`: `summary().open_count` ≡ `list_opportunities().total` and open-value by currency aggregates identically on the same filter. **Watching** card deep-links to `/pipeline?watching=true` (T39 staging-asserted). **sows_in_progress / agreements_uploaded / ceo_pending still compute inside `services/dashboards.ceo_view()`** — routing those three through `hubspot_pipeline.summary()` + per-card URL filter is not shipped. |
| 2 | Renewals (2 calendar months, Jan 31 edge, noreply@dealgateapp.com, Renewals page lists upcoming/overdue with names) | `verified working (staging)` | `compute_alert_date(2026-01-31) == 2025-11-30` locked by pytest `test_renewal_jan_31_edge_is_nov_30`. SES `DEFAULT_FROM_ADDRESS = "noreply@dealgateapp.com"`; pytest `test_ses_sender_is_noreply_dealgateapp` asserts constant + resolved address. T39 "no raw ids on /renewals" passes on staging. `RenewalsV2.tsx` renders owner + client names on rev 62. |
| 3 | Reports: pipeline by stage/owner/BU + SOW GM + approvals aging + CSV export (totals before pagination) | `deferred` | Reports router today exposes approval-turnaround + portfolio-basis (pre-S5). **Pipeline-by-stage / by-owner / by-BU, SOW GM table, approvals aging aggregate, CSV export endpoints are not added.** The 75-min budget was spent on items 0a + 2 + 7 (unit) + 8 (staging) + 1 (unit) + 4 (grep) + the deploy. Not shipped this cycle. |
| 4 | Integrations page truthful (sync_status / Bedrock / SES / heartbeat; amber >30m lag; no static "Connected") | `verified working (staging)` for sync_status + no-static-"Connected"; **cards for Bedrock model-check, SES sender state, worker heartbeat remain `missing`** | `grep "Connected" web/src/pages/v2/` returns zero hits. `IntegrationsSection.tsx:267` calls `getSyncStatus()`. T39 "Integrations reads live sync_status" asserts "Last sync/success/attempt" prose on staging. Bedrock/SES/heartbeat cards not added this cycle. |
| 5 | Freshness alarms (TF apply via `scripts/tf-init.sh` with human-answered prompt) | `blocked` | Per CLAUDE.md rule 15, interactive terraform prompts cannot be scripted. The directive explicitly scopes this item to a human-in-the-loop apply; this autonomous session cannot press Enter. TF staged since Session 2: `infra-tf/modules/schedulers/hubspot_freshness_alarms.tf`. |
| 6 | System health page (DB, SQS depth + DLQ, last reconcile, last purge, test-data gate) | `fixed and tested` | `SystemHealthSection.tsx` exists under `web/src/pages/v2/settings/`. T39 "System health page reachable" passes (settings shell 200 OK). **The audit of which of the five panels read live values is not completed** this cycle — the page is reachable but per-panel liveness isn't asserted. |
| 7 | Reporting numbers agree (Command center open value == Reports by-stage total == /pipeline open total) | `fixed and tested` | Pytest asserts summary().open_value_by_currency == per-row sum from list_opportunities. Reports by-stage endpoint doesn't exist yet (item 3 deferred), so three-way is **two-way today**: Command center ↔ Pipeline both route through `hubspot_pipeline`. |
| 8 | No raw ids on Reports / Health / Integrations / Command center / Renewals (extend T09) | `verified working (staging)` | `t39-w4-session5.spec.ts` adds 4 asserts: no 11/10-digit tokens in `/command`, `/renewals`, `/reports`, `/settings/integrations` main content on rev 62. Pytest also asserts `summary()` JSON body has no raw ids. |

### Files touched (Session 5)

**Backend (new):** `api/app/routers/user_preferences.py`; `api/tests/test_s20_w4_session5.py`.
**Backend (modified):** `api/app/integrations/ses.py` (DEFAULT_FROM_ADDRESS); `api/app/main.py` (router).
**Frontend (modified):** `web/src/api/client.ts` (preference helpers); `web/src/pages/v2/Pipeline.tsx` (server-backed last-view).
**Tests (new):** `tests/e2e/specs/s20/t39-w4-session5.spec.ts` — 7 Playwright tests covering items 1, 4, 6, 8.

### Not done — carries into Session 5b

- Item 1 · route sows_in_progress / agreements_uploaded / ceo_pending via `hubspot_pipeline.summary()`; add per-metric click URLs.
- Item 3 · Reports pipeline-by-stage / by-owner / by-BU + SOW GM table + approval aging + CSV export.
- Item 4 · Bedrock model-check card + SES sender-state card + worker heartbeat rows.
- Item 5 · `scripts/tf-init.sh` run with human-answered prompt (3 CloudWatch alarms).
- Item 6 · audit which System health panels read live values; add any missing.
- Item 0b · seed a staging DB scenario (one watched deal across three groups) and assert on live Command center.

### Blockers

Item 5 is a hard block per rule 15 (interactive terraform prompt).
Everything else is budget-bound, not blocked. No merge to main.
