# S22-P4 · Click-through fixes + upload the sheet — report

**Session:** S22-2 · **Branch:** `feat/s22-p4` (worktree `/Users/srikanthparimi/OfficeApp/dealgate-s22-p4`, off `origin/main` 5124907), pushed ·
**Staging now:** API `officeapp-dev-api:100` on image `s22p4-68ff809d` (`sha256:c846036816cf494da55985028a82fdf2a99c907bd46f7462bc73c6dd907cadea`), SPA `assets/index-CwMcUryo.js`, all ten worker families + `api-migrate` on the same image, no new migration (head `20261012_0065_portfolio_forecast`) ·
**Written:** 2026-10-12 · companions: `deploy.md` §"S22-P4 candidate" and §"S22-P4 apply and roll" (plan, checksums, task ids, digest), `docs/bugs/s22.md` (decisions D9–D11; no new bug numbers), scoreboard rows S22-P4-1 … S22-P4-5.

## What the pack changed and what was built

The pack replaced the engine (`api/app/services/forecast/__init__.py`, unmodified since: one-time additional costs are now spread across the term by share of month), added `workbook_import.py` with four tests (one on the product owner's own sheet in `fixtures/`), and updated the prototype, the contract and the directive. `python -m pytest api/tests/forecast -q` → **22 passed** before any line was written; the engine was not touched afterwards.

| Commit | Item |
| --- | --- |
| 9e2df8d | pack + scoreboard rows |
| ef5cf41 | P4-1 contract spec follows the spread (D11) |
| 4094afa | P4-2 short engagements: whole-term summary first, "Show month split" |
| da686af | P4-3 portfolio headers "Revenue · <Month>", "GM % · whole term", slice subtitle |
| 68ff809 | P4-4 `POST /engagements/import-workbook`, upload box on New engagement, hours check once; P4-5 "Per person · hours by month" |

Deploy: image-only plan (12 to add, 14 to change, 12 to destroy — the eleven task definitions + the migration trigger replaced, the service, event targets and task-role policies updated) applied by the session per this round's rule (Kanna: plan for Kanna only if infrastructure changes). No infrastructure changed.

## Every item (rule 16 vocabulary)

| Item | State | Proof (staging unless noted) |
| --- | --- | --- |
| P4-1 | verified working (staging) | engine from the pack deployed in `s22p4-68ff809d`; `s22-p1-contract.spec.ts` on staging: totals and 12 month×assignment rows to the cent, the January portfolio row equals the engagement's own January line including its share of the spread one-time cost; 22 forecast tests + 4 workbook-import tests locally; engine file byte-identical to the pack |
| P4-2 | verified working (staging) | `s22-p4-upload.spec.ts` on staging: the owner's one-month assessment shows "Short engagement … judged on the total" and the whole-term summary table first, no month table until "Show month split", then the months and "Hide month split"; long engagements unchanged (`s22-p2-owner-path` still sees "Monthly view required" and the month tables) |
| P4-3 | verified working (staging) | `s22-p2-owner-path.spec.ts` on staging asserts the Portfolio table headers "Revenue · <month>" and "GM % · whole term" and the subtitle "the month columns show only <Month>'s slice of each engagement" |
| P4-4 | verified working (staging) | `s22-p4-upload.spec.ts` on staging: the sample staff-aug sheet uploaded on `/engagements/new` becomes an engagement with the sheet's project name, five people, PASS, note "matches the sheet", dismissed once and gone after reload; the owner's older copy imports with "Sheet said 168 h for Vikrin; the app computes 160 h — weekday holiday(s) in the window: 2026-09-07" and the "Employment type" warning; `POST /api/engagements/import-workbook` on staging answers 401 unauthenticated; audit `engagement.imported_workbook`; 4 pytests (sample sheet, owner copy hours check, blank template rejected in the sheet's words, test identity needs a fixture account); CSV import unchanged |
| P4-5 | verified working (staging) | `s22-p4-upload.spec.ts` on staging: the assessment engagement's Forecast tab heading reads "Per person · hours by month" once the split is shown; staff-aug stays "Per person · revenue by month" (vitest) |

Every item is `verified working (staging)`. None is fixed-and-tested only, missing, blocked or deferred.

## Decisions this round (docs/bugs/s22.md)

| # | Decision |
| --- | --- |
| D9 | per-file ruff ignores for the pack's finished files (engine, `workbook_import.py`, their tests) instead of editing them |
| D10 | a sheet's staffing rows become roster people named by the Role column (find-or-create), as the CSV importer does; teardown removes them |
| D11 | the contract spec compares the January portfolio row to the engagement's own January line and allows a cent per serialised month when reconciling month lines to totals |

## Test evidence

| Suite | Result |
| --- | --- |
| `api/tests/forecast` | 22 passed (18 goldens + 4 workbook-import) |
| `api/tests/test_s22_portfolio_forecast.py` | 21 passed (17 + 4 new) |
| full `api` suite from `api/`, fresh Postgres `dealgate_p4` | 2618 passed, 1 skipped, 144 xfailed; 2 failed in `tests/test_auth.py` (503) — pre-existing environment dependency, identical on `origin/main` in a fresh checkout: those two tests need a schema in the gitignored SQLite `api/dev.db`, which a new worktree does not have; with a populated file `tests/test_auth.py` → 5 passed. No branch file is involved (note in `docs/bugs/s22.md`) |
| `ruff check` (`api/`, ruff 0.16.8) | every file this branch changed: `All checks passed!`; repo total 218 findings, down from 237 on `origin/main` (D9 ignores) — the remaining 218 are pre-existing on main (unused imports in older tests/migrations), none on branch files |
| `web` vitest | 89 files / 556 tests passed; `tsc --noEmit` clean; production build clean |
| Playwright `specs/s22/*` local full stack | `s22-p4-upload` (2) + `s22-p1-contract` + `s22-p2-owner-path` pass, teardown clean |
| Playwright on staging (`s22p4-68ff809d`) | `4 passed (1.6m)`; owner path re-run with the P4-3 assertions passed |
| `scripts/deploy-smoke.sh` | `smoke 20261012T224136Z` GREEN |
| `scripts/check-test-data-clean.sh` (extended) | clean after every staging run: 0 clients / 0 approvers / 0 people / 0 engagements |

## Next

Kanna's click-through on staging: `https://app.dealgateapp.com/engagements/new` → upload her sheet (the note appears once on the engagement header); the Forecast tab of the short engagement ("Show month split"); `/portfolio` headers. No merge to main before that click. Merge = squash `feat/s22-p4` → `main`, then the main-image roll as for S22.
