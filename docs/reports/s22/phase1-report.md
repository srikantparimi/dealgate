# S22 · Portfolio & Forecast — Phase 1 report (CODE COMPLETE)

**Session:** S22-1 · **Branch:** `feat/s22` (worktree `dealgate-s22`, off `origin/main` @ 7a19dbd) ·
**Written:** 2026-10-12 · **Directive:** `docs/directives/s22-portfolio-forecast.md` ·
**Rules in force:** the session's working rules (no budget; anti-stuck 2 attempts / 15 min; phase 1 = build everything, test only "it compiles and the 18 engine tests pass"; commit per item).

Phase 1 is done: every item P1-1 … P3-6 is built end to end and committed with its number. Nothing is deployed yet; nothing is `verified working (staging)` yet — that is phase 2.

## State of every item (rule 16 vocabulary)

| Item | State | Proof |
| --- | --- | --- |
| P1-1 | fixed and tested | 71944e3 pack committed unchanged (3 pre-existing empty `__init__.py` preserved). `python -m pytest api/tests/forecast -q` → 18 passed, also with `DEALGATE_POSTGRES_URL` (local pgvector/pg16). Engine not modified. |
| P1-2 | fixed and tested | 145a5af migration `20261012_0065_portfolio_forecast` + `app/models/engagement.py`. `test_migration_parity` 3/3 and `test_audit_hardening` 1/1 on Postgres; `alembic heads` == 1. Seeds: US 36/5/35, India 8/8/50, floor 35, 8 h/day, rate card, holidays 2026–27. |
| P1-3 | fixed and tested | f13272f `services/engagement_forecast.py`. `test_client_a_golden_through_the_api`: totals, 12 month×assignment rows, 5 per-row totals, location check, months ⇄ totals — to the cent. `forecast_run` cache hit + invalidation on allocation and on calendar change. |
| P1-4 | fixed and tested | f13272f `routers/engagements.py`, 24 routes. 16/16 pytest: permissions × 7 roles, 422 bodies carry the engine's `missing` strings verbatim, Sales redaction, close / rehire / delete-409 / supersede-on-rate-change, list filters + status, portfolio. Deviations D1–D6 in `docs/bugs/s22.md`. |
| P1-5 | fixed and tested | 4cdbe63 `tests/e2e/specs/s22/s22-p1-contract.spec.ts` (Cognito system bot, run tag `S22 e2e <ts>`, teardown + leak sweep). **Not yet run on staging.** |
| P1-6 | fixed and tested | f13272f `POST /allocations/import`: workbook headers (with their commas), blank-Role rows ignored, W-2/1099 labels, `Utilization %` as 100 or fraction, 422 on unknown location. Grid button "Import staffing CSV" (09a5574). |
| P2-1 | fixed and tested | 09a5574 `AllocationsTab.tsx`. vitest: grid, Row GM red under floor, Leaves / Re-hire / remove hit the API, totals row, Sales sees "restricted", HR has no controls. `tsc --noEmit` clean. |
| P2-2 | fixed and tested | 09a5574 `ForecastTab.tsx`. vitest: monthly-required line, all-resources block ("Labour + burden"), assignment block, per-person block. |
| P2-3 | fixed and tested | 09a5574 `SetupTab.tsx`: project block with type greying, PATCH per field; costs add / inline edit / remove (frequency + billed-to-client required). |
| P2-4 | fixed and tested | acc9704 `NewEngagementPage.tsx` (+ New client…, From a Closed-Won deal picker, `?deal=` pre-fill) and `DealDetail` "Create engagement from deal". vitest: greying, Missing list, new-client creation. |
| P2-5 | fixed and tested | c85e9c1 Settings → "Forecast calendar" (`/settings/forecast`), one PUT; server re-runs every active engagement (pytest). |
| P2-6 | fixed and tested | a4c9f56 `tests/e2e/specs/s22/s22-p2-owner-path.spec.ts` (owner path, rule-18 assertions, teardown restores the calendar). **Not yet run on staging.** |
| P3-1 | fixed and tested | c11121e `PortfolioPage.tsx`: month / type / client filters in the URL, table, server totals row, Export CSV, + New engagement. |
| P3-2 | fixed and tested | c11121e + f13272f `portfolio_month()` single query service; pytest asserts each card equals its list; vitest: Below-floor card filters the table to the rows it counted. |
| P3-3 | fixed and tested | c11121e roll-offs + bench panels by name (person, client, engagement). |
| P3-4 | fixed and tested | d66ddaf `worker/portfolio_scheduler.py::process_renewals` — D8 two-calendar-month rule via `renewals.compute_alert_date`; deal-backed → `open_renewal` (renewal row); manual → owner task + notification; idempotent. 4 pytests incl. the 05-01 / 05-02 boundary. Terraform family added, **not applied**. |
| P3-5 | fixed and tested | d66ddaf `process_nightly_digest` → `daily_digest` through the outbox, once per owner per day. 2 pytests. EventBridge rule `cron(0 6 * * ? *)` in Terraform, **not applied**. |
| P3-6 | fixed and tested | f13272f `test_portfolio_month_reconciles_three_ways_and_exports_csv`: portfolio month total == Σ engagement month lines == Σ allocation-month rows (+ pass-through / additional costs), CSV carries the totals row; c11121e Export CSV button. |

## Test evidence (local)

| Suite | Result |
| --- | --- |
| `api/tests/forecast` (engine goldens) | 18 passed |
| `api/tests/test_s22_portfolio_forecast.py` | 16 passed (SQLite and fresh Postgres) |
| `api/tests/test_s22_portfolio_scheduler.py` | 6 passed |
| `api/tests/test_migration_parity.py`, `test_audit_hardening.py` | 4 passed (Postgres) |
| full `api` suite | green except two environment artefacts, both re-verified green: `test_auth` needed the gitignored `api/dev.db` (created with `create_all`); `test_approval_concurrency` needs a disposable Postgres (passes on a fresh database; 15 ≠ 5 came from three suite runs on the same DB) |
| `web` `tsc --noEmit` | clean |
| `web/src/__tests__/v2/S22Portfolio.test.tsx` | 11 passed |
| `ruff check` on every new/changed Python file | clean (repo-wide count unchanged vs origin/main) |
| `terraform fmt -check` module.schedulers | clean |

## Decisions and deviations

See `docs/bugs/s22.md` D1–D8. Highlights: `GET /clients` keeps its paginated envelope (flat shape at `/portfolio/clients`); `/resources` and `PATCH/DELETE /costs/{id}` added; Forecast JSON carries loaded-cost / GM-money / staffing and per-assignment totals so the browser never computes; the OpenAPI example's India loaded cost (37912.56) is a typo — engine and goldens say 37912.32; Sales/SalesLeader/Presales get per-person cost keys stripped (blueprint §3); the S21 weekly forecast module moved to `app/services/weekly_forecast.py`.

## Phase 2 plan (next)

1. Deploy via D5: immutable image `s22-<sha>` → alembic (0065) → API + worker task-defs → SPA with cache headers → CloudFront. The new `officeapp-dev-portfolio-scheduler` family needs `terraform apply` on module.schedulers — rule 15: the prompt is a stop point for Kanna.
2. `scripts/deploy-smoke.sh` → `s22-p1-contract.spec.ts` → `s22-p2-owner-path.spec.ts` → `scripts/check-test-data-clean.sh`.
3. Every failure → numbered line in `docs/bugs/s22.md`, fixed in order, redeploy when clear.
