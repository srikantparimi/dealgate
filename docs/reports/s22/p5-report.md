# S22-P5 · business units, the forecast-model master, actuals — report

**Session:** S22-3 · **Branch:** `feat/s22-p5` (worktree `/Users/srikanthparimi/OfficeApp/dealgate-s22-p5`, off `origin/main` dfc3f8b), pushed ·
**Staging now:** API `officeapp-dev-api:106` on image `s22p5c-a19358cc` (`sha256:3012304055785729a76f8ea079c1214b6823b72b8aa87b8a3bdcec909d74ac0f`; P5b `s22p5b-63b786af` rev 104, P5a `s22p5a-a1c856f8` rev 103, P5 proper `s22p5-d0270a48` rev 102), SPA `assets/index-freWl-_8.js`, SPA `assets/index-Cv_2NWJ5.js`, all ten worker families + `api-migrate:40` on the same image, migration head `20261012_0066_bu_actuals` ·
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

## S22-P5a (2026-10-12 evening pack, rides on `feat/s22-p5`)

Pack applied as given (importer replaced, test extended, `scripts/load_forecast_model.py`, directive). `python -m pytest api/tests/forecast -q` → **34 passed**. The master workbook (`~/Downloads/ST21 FY2526 Forecast Model (Master) 09.18.26.xlsx`, the newest file there) is gitignored by name and was never copied into the repo; reports were written to `/tmp`.

| Item | State | Proof |
| --- | --- | --- |
| P5a-1 | verified working (staging) | staging API rev 103 · image s22p5a-a1c856f8 (digest cc35618a…b10) · 2026-10-13 · server dry run of the real master through scripts/load_forecast_model.py: ST21 7 clients (9 on the previous image), ITA/RR gone from the report; 34 forecast tests incl. test_the_roll_up_block_below_the_total_is_not_a_client_list; importer byte-identical to the pack; smoke 20261013T025103Z GREEN; s22-p5-forecast-model 3 passed on staging; gate clean |
| P5a-2 | verified working (staging) | staging API rev 103 · image s22p5a-a1c856f8 (digest cc35618a…b10) · 2026-10-13 · the three documented commands run against the newest master in Downloads: --offline (28 tabs → 81 engagements, 393 people, report in /tmp, nothing created); server dry run (nothing created); --load refused by the S21 runtime isolation for the e2e bot (bug log row 7, by design) — needs a real user's bearer or the Load button; master gitignored by name, never committed; requests added to dev deps |

The three documented commands, run against the newest master in Downloads:

| Command | Outcome |
| --- | --- |
| `--offline --as-of 2026-09` | parsed locally: 28 client tabs → 81 engagements, 393 people; ST21 **7** clients (the fix), IT Avalon 18, Retro Rabbit 1, Unassigned 2; report `/tmp/forecast-model-dryrun-offline.md`; nothing created |
| server dry run (`--base-url https://app.dealgateapp.com --as-of 2026-09`, bot bearer) | on `s22p5-d0270a48` (pre-fix): ST21 9 clients, IT Avalon 25, Retro Rabbit 12, Unassigned 2 (the card counts dashboard clients, so dashboard-only clients are included); after the P5a roll (`s22p5a-a1c856f8`): ST21 **7**, ITA/RR gone; reports `/tmp/forecast-model-dryrun-staging*.md`; nothing created |
| `--load --yes` (bot bearer) | dry run repeated, then the create was refused by the S21 runtime isolation: the e2e bot is a test identity and may only touch fixture accounts (bug log row 7). Nothing was created. The load needs a real user's bearer, or the Load button on `/import/forecast-model` as yourself |

## S22-P5b (as_of is a parameter, not a global)

Pack applied as given (importer + its test + CLI replaced, directive added). `python -m pytest api/tests/forecast -q` → **36 passed** first.

| Item | State | Proof |
| --- | --- | --- |
| P5b-1 | verified working (staging) | staging API rev 104 · image s22p5b-63b786af (digest 42023218…5444) · 2026-10-13 · importer from the pack deployed unmodified; 36 forecast tests incl. test_as_of_is_per_call_and_never_leaks_between_imports + test_the_report_says_which_month_the_actuals_run_to; staging dry run of the real master without as_of opens with 'Actuals are taken through 2026-09; every later month is forecast' |
| P5b-2 | verified working (staging) | staging API rev 104 · image s22p5b-63b786af (digest 42023218…5444) · 2026-10-13 · service passes the request's as_of through, None when absent (no _AS_OF read, no month in the service); test_as_of_defaults_to_the_models_month_and_never_leaks_from_an_earlier_request (2025-10 then none → 2026-09; Alpha actual months 2 then 3; 'Sept' → 422); the import screen sends no as_of and resolves to 2026-09 on staging |
| P5b-3 | verified working (staging) | staging API rev 104 · image s22p5b-63b786af (digest 42023218…5444) · 2026-10-13 · CLI from the pack: --as-of has no default and is only sent when given; offline run without the flag → 28 tabs / 81 engagements / 393 people and the 2026-09 line; staging dry run without the flag → same counts (Σ tab people 393, ST21 7 clients), report identical to the P5a run; nothing created |

Every item is `verified working (staging)`.

## S22-P5c (the import refuses rather than guessing)

Pack applied as given (importer + its test + prototype v5). `python -m pytest api/tests/forecast -q` → **39 passed** first. No default, no override: a blank business unit or location stops the load and names the cells.

| Item | State | Proof |
| --- | --- | --- |
| P5c-1 | verified working (staging) | staging API rev 106 · image s22p5c-a19358cc (digest 30123040…ac0f) · SPA index-freWl-_8.js · 2026-10-13 · importer from the pack deployed unmodified; 39 forecast tests; staging dry run of the real master lists 7 blockers (UEBIZ + Children's Hospital-VMS no BU; 26 people without a location) and leads the report with them; the synthetic fixture's Zeta Unlisted yields both kinds on staging (s22-p5c-blockers) |
| P5c-2 | verified working (staging) | staging API rev 106 · image s22p5c-a19358cc (digest 30123040…ac0f) · SPA index-freWl-_8.js · 2026-10-13 · no ST21 default (an engagement without a dashboard BU can only stop the load); dry run returns blockers at 200; load with blockers → 422 {blockers} with nothing written — test_a_load_with_blockers_is_422_and_writes_nothing (client/engagement/person/location/holiday counts unchanged) and the direct call in s22-p5c-blockers on staging; contract carries the second 422; CLI `--load` on the real master printed `Not loaded — fix these in the workbook first (7)` with each fix on its own line, exit 2, nothing created |
| P5c-3 | verified working (staging) | staging API rev 106 · image s22p5c-a19358cc (digest 30123040…ac0f) · SPA index-freWl-_8.js · 2026-10-13 · s22-p5c-blockers on staging: the panel 'Fix these in the workbook before loading' lists both blockers with the fix beneath each, Load disabled, '2 things to fix · re-upload when the workbook carries them'; vitest (S22P5.test.tsx) asserts the panel, the disabled button and that nothing is posted dry_run=false |
| P5c-4 | verified working (staging) | staging API rev 106 · image s22p5c-a19358cc (digest 30123040…ac0f) · SPA index-freWl-_8.js · 2026-10-13 · tests/e2e/specs/s22/s22-p5c-blockers.spec.ts: 2 passed on staging (panel + disabled Load; direct dry_run=false → 422 {blockers}, engagement count unchanged); the owner path (s22-p5-forecast-model) loads the complete copy of the fixture: 3 passed; all five S22 specs 9 passed (2.1 m); gate clean |

Every item is `verified working (staging)`. Open in the bug log: row 8 (the full master's import timing — ~24 s dry run; the load is not timeable until the sheet is fixed).

On the real master as it stands (never committed): the dry run lists **7 blockers** — UEBIZ and Children's Hospital-VMS with no dashboard row, and 26 people without a location across Liberty Mutual, UEBIZ, Caesars, Caesers Entertainment and First Citizens; `--load` is refused with each fix on its own line and nothing is created. Once the dashboard carries the two clients and the Location column is filled, the same command loads.

## For the product owner's click-through

`https://app.dealgateapp.com/import/forecast-model` → upload `ST21_FY2526_Forecast_Model_Master.xlsx` (never committed; the dry run creates nothing) → read the report → Load → `/portfolio` (BU tabs, subtotals, Billing loss card) → any imported engagement: people have no cost (INCOMPLETE until the rate card covers them, as the directive says); Setup shows BU / owners / status; the grid shows Person first and "per"; the Forecast tab shows the Actuals block for months the model had actuals. Locations arrive as US, India - Pune, India - Chennai, South Africa and are added to Settings on first import with placeholder burden/floors (the report says so).

No merge to main before that click.
