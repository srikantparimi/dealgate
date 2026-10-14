# S23-PL1 — Make the Pipeline data trustworthy (backend only)

Branch `feat/s23-pl1` from main (staging runs main 6a3c63f). Small, backend only, and it merges **before** PL2 because PL2 reads its `GET /api/hubspot/sync-health`. Contract: `docs/reference/openapi-pipeline.yaml` (`Freshness`, `/api/hubspot/sync-health`).

## Why

The Pipeline page says "Last synced 12d ago". The deals were refreshed last night. The label reads an intake heartbeat frozen since 2026-10-01, so it can never warn about real age. Worse, the nightly sync reports success even when it fails, and one bad stage or company can abort the whole run silently. People are being told the wrong thing in both directions.

## Rules (they apply every time)

1. **No session token or time budget. Do not get stuck.** One bounded attempt per issue; if it does not yield, log it in `docs/bugs/s23-pl1.md` with what you tried and move on. Finish ALL fundamental code first (code-complete), then test and fix the logged bugs one by one. Efficient and quick.
2. **Anti-glossing.** Report every numbered item below by its number in exactly one of five states: **verified working / fixed and tested / missing / blocked / deferred**, each with proof (test name + result, command output, or file:line). No "complete" or "zero deferrals" summary may replace the list. An item missing from your report counts as not done.
3. **Heartbeat.** One line at every step boundary and at least every 15 minutes while a long command runs: `PL1 · step · result · next`.
4. CLAUDE.md applies: no infra via console or CLI (rule 12), never a scripted-yes terraform (rule 15), branch → staging → smoke → Kanna's click → squash merge (rule 14). HubSpot token is test-only, never printed, committed or reused. Do not change HubSpot app settings. Do not touch `Pipeline.tsx` beyond item 8.

## Items

1. **Sync run record.** Every deal reconcile writes one row: kind, started_at, finished_at, status (`ok | partial | failed`), deals_seen, deals_written, error_count, first errors (HubSpot id + short reason, no names, max 5). Use the existing table if there is one; add a migration only if there is not.
2. **`GET /api/hubspot/sync-health`** exactly as the `Freshness` schema. `last_success_at` is the finish time of the last run that completed without a fatal error and wrote deals. `state`: `fresh` when last success is within 36 h and the last attempt succeeded; `failed` when the last attempt failed or ended partial; `stale` when the last success is older than 36 h. Readable by every role that can read the Pipeline.
3. **The nightly sync fails loudly.** Any unhandled exception ends the run as `failed`, records the error, and exits non-zero so the task shows failed. It never records or logs success when it did not succeed.
4. **Per-record isolation.** One bad stage, company or deal is caught, counted and listed with its HubSpot id, and the run continues. A run that wrote deals but had errors ends `partial`, not `ok`. A run that could not read HubSpot at all ends `failed`.
5. **Stage mapping everywhere deals are written.** Prove with a test that the nightly path keeps closed won and closed lost deals closed and Hold as Hold.
6. **Webhooks stay off.** Today they get 401 and the handler drops the stage mapping, so turning them on would reopen closed deals. Either route the webhook writer through the same stage-mapping writer as item 5, or leave the handler unable to write deals. Say which, with a test. Do not enable anything.
7. **Intake schedule and continuous service.** Both are off. Report in the bugs file the exact Terraform change that would re-enable each and whether it is needed now that nightly works. **Do not apply it.** Kanna decides (rule 15).
8. **Retire the heartbeat as a freshness input.** `grep` every consumer of the intake heartbeat. Remove it from freshness logic. In `Pipeline.tsx:189` change only the label source so the old page reads `sync-health` (`last_success_at`) until PL2 replaces that file. List every consumer you changed or left, by file:line.
9. **Staging proof.** Run one nightly deal sync through the sanctioned path (the existing admin trigger or script; if there is none, stop and ask, do not invent one). Show `sync-health` returning `fresh` with a current `last_success_at`, then show it returning `failed` after an injected failure in a **test** run (not a production run).
10. **Tests.** Run records for ok / partial / failed; freshness state at 1 h, 35 h, 37 h and after a failed attempt (frozen clock); per-record isolation (one poisoned deal, others saved); closed stage preserved; webhook guard; heartbeat no longer affects freshness.

## Done means

Items 1–10 reported by number in the five states with proof, branch deployed to staging via `scripts/deploy-smoke.sh`, smoke green, and a one-paragraph note of anything surprising. **Do not merge.** Kanna clicks first.
