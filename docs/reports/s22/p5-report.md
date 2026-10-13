# S22-P5 · business units, the forecast-model master, actuals — report

**Session:** S22-3 · **Branch:** `feat/s22-p5` (worktree `/Users/srikanthparimi/OfficeApp/dealgate-s22-p5`, off `origin/main` dfc3f8b), pushed ·
**Staging now:** API `officeapp-dev-api:102` on image `s22p5-d0270a48` (`sha256:9b2a594cb66f70aebbb3d5124224861583ed4a591556e1c055151585507c94ca`), SPA `assets/index-Cv_2NWJ5.js`, all ten worker families + `api-migrate:40` on the same image, migration head `20261012_0066_bu_actuals` ·
**Written:** 2026-10-13 · companions: `deploy.md` §"S22-P5 candidate" / §"S22-P5 apply and roll", `docs/bugs/s22-p5.md` (rows 1–6), scoreboard rows S22-P5-1 … S22-P5-9.

## Order of authority, as applied

Engine (`api/app/services/forecast/__init__.py`) and importer (`forecast_model_import.py`) are byte-identical to the pack; `python -m pytest api/tests/forecast -q` → **33 passed** before any line was written. Screens copy prototype v4 restyled to the DealGate v2 tokens; every response is the engine's `Forecast` serialised (contract v1.1). Where the three were silent: the New-engagement page's business unit and owners ride along with the cost-margin sheet upload; a fee-less MSP is saveable at setup and the forecast carries the engine's "monthly_fee required (or monthly rates on the people)" until people with rates exist.

| Commit | Item |
| --- | --- |
| 716f233 | pack + scoreboard rows |
| 139c953 | P5-2 migration 0066 + models |
| 7b11f18 | P5-3 / P5-4 contract routes, actuals in the engine path, BU grouping, billing-loss card, PUT actuals, forecast-model import, 9 pytests |
| 0d22483 / 2c91b31 / 2d34892 | P5-5 / P5-6 / P5-7 screens (web), vitest |
| 1584af8 | P5-6 sheet upload carries BU + owners |
| d0270a4 | P5-8 Playwright + owner-path spec on the v4 grid; scoreboard |
| 45e203e | bug log + deploy-record candidate |

## Every item (rule 16 vocabulary)

| Item | State | Proof |
| --- | --- | --- |
| 1 | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · engine from the pack deployed unmodified; 33 forecast tests; s22-p1-contract on staging still equals the goldens; the imported assessment on staging reports INCOMPLETE with 'cost per hour unknown' (P5-8 run) |
| 2 | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · migration task 40ddd4bb265740fc84bad1d1091ba1da succeeded on staging (head 20261012_0066_bu_actuals); parity 3 passed on Postgres; the P5-8 load wrote business units, owners, closed, rate basis, person and actuals through the new columns |
| 3 | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · s22-p5-forecast-model on staging: /portfolio/it-avalon (business_unit filter + one group), /portfolio groups + totals + cards.billing_loss; Forecast.actuals rendered; 9 pytests incl. PUT actuals + permissions |
| 4 | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · s22-p5-forecast-model test 1 on staging: dry run (3 BUs, tabs, report) created nothing, Load created clients/engagements/allocations/actuals + the model's locations and holidays (calendar restored by teardown); idempotency + non-master 422 by pytest |
| 5 | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · s22-p5-forecast-model tests 2–3 on staging: BU tab URL /portfolio/it-avalon with its single subtotal, /portfolio with ST21 / IT Avalon / Retro Rabbit group headers, three subtotals adding to the grand total, Billing-loss card, owners under the name, Delta Closed off the page |
| 6 | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · s22-p2-owner-path on staging through the v4 grid (Person first, planning resource, per, bill rates) and Setup; s22-p5 test 2 shows the Actuals block on the Forecast tab; New-engagement BU/owners by vitest + the owner path's create |
| 7 | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · s22-p5-forecast-model test 1 on staging: /import/forecast-model upload → dry-run cards/table/report → 'Load …' → lands on /portfolio |
| 8 | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · tests/e2e/specs/s22/s22-p5-forecast-model.spec.ts: 3 passed on staging (with s22-p4-upload 2, s22-p1-contract, s22-p2-owner-path: 7 passed, 1.8 m); gate clean after |
| 9 | verified working (staging) | staging API rev 102 · image s22p5-d0270a48 (digest 9b2a594c…94ca) · SPA index-Cv_2NWJ5.js · migration 0066 applied by task 40ddd4bb · 2026-10-13 · test_model_import_load_creates_the_ledger_and_the_portfolio_groups_reconcile (subtotals == Σ rows, grand total == Σ subtotals, billing_loss.engagements == rows with actuals) + spec test 3 asserts Σ subtotal revenue == grand total on the staging screen |

Every item is `verified working (staging)`. None is fixed-and-tested only, missing, blocked or deferred.

## Bug log (docs/bugs/s22-p5.md)

Rows 1–5 fixed inside their bounded attempt (revision id length; fee-less MSP at setup; sample sheet accepted as a master; dry run missing dashboard-only BUs; owner-path spec vs the v4 grid). Row 6 is the pre-existing `test_auth` dev.db dependency (same on main), noted.

## Test evidence

| Suite | Result |
| --- | --- |
| `api/tests/forecast` | 33 passed |
| `api/tests/test_s22_p5_business_units.py` | 9 passed (dry run 3 BUs + nothing created; load + locations + closed + cost unknown + reconciliation + idempotent re-import; PUT actuals; BU/owners/closed/rate basis/fee-less MSP; permissions ×4 roles; non-master 422) |
| `api/tests/test_s22_portfolio_forecast.py` | 21 passed |
| `tests/test_migration_parity.py` (Postgres) | 3 passed — 0066 matches the models |
| full `api` suite, fresh Postgres | 2638 passed, 1 skipped, 144 xfailed; 2 pre-existing `test_auth` failures (503, need a schema in the gitignored `api/dev.db`; 5 passed with one) |
| `ruff check` | clean on every changed file; per-file ignores for the pack's importer files (as D9) |
| `web` vitest / tsc | 91 files / 574 tests passed; `tsc --noEmit` clean; production build clean |
| Playwright, local full stack (Postgres at 0066) | `s22-p5-forecast-model` 3, `s22-p4-upload` 2, `s22-p1-contract` 1, `s22-p2-owner-path` 1 — all pass |
| `scripts/deploy-smoke.sh` on `s22p5-d0270a48` | `smoke 20261013T005136Z` GREEN; gate clean |
| Playwright on staging | `s22-p5-forecast-model` (3) + `s22-p4-upload` (2) + `s22-p1-contract` + `s22-p2-owner-path`: `7 passed (1.8m)` |
| `scripts/check-test-data-clean.sh` after | clean: 0 clients / 0 approvers / 0 people / 0 engagements; calendar snapshot restored by the spec's teardown (no teardown warnings) |

## For the product owner's click-through

`https://app.dealgateapp.com/import/forecast-model` → upload `ST21_FY2526_Forecast_Model_Master.xlsx` (never committed; the dry run creates nothing) → read the report → Load → `/portfolio` (BU tabs, subtotals, Billing loss card) → any imported engagement: people have no cost (INCOMPLETE until the rate card covers them, as the directive says); Setup shows BU / owners / status; the grid shows Person first and "per"; the Forecast tab shows the Actuals block for months the model had actuals. Locations arrive as US, India - Pune, India - Chennai, South Africa and are added to Settings on first import with placeholder burden/floors (the report says so).

No merge to main before that click.
