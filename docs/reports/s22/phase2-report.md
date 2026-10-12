# S22 · Portfolio & Forecast — Phase 2 report (TEST AND FIX)

**Session:** S22-1 · **Branch:** `feat/s22` @ `8f644b2` (worktree `/Users/srikanthparimi/OfficeApp/dealgate-s22`) · **Written:** 2026-10-12 ·
**Candidate image:** `officeapp-dev-api:s22-520f5174` (`sha256:5d35069925329ca4fe1480eee6f123c97c98bb5dd34adee3d1e026ac0a6e941f`) ·
**Saved plan:** `/tmp/s22-520f5174.tfplan` (`c9ffd820…339eb`, 14 add / 13 change / 11 destroy) — see `docs/reports/s22/deploy.md`.

## Where phase 2 stopped

The deploy path that the last three S22 releases used (D5 as amended by S21F-02, rule 15) is: immutable image → reviewed whole-root Terraform plan → **human apply approval** → migration gate → API roll → SPA publish → CloudFront → smoke → specs on staging → owner click-through. Everything up to the approval is done and recorded; the apply is Kanna's prompt to answer, not mine. Nothing was mutated on AWS: the only writes were the image push to ECR and reading state for the plan.

While waiting, the two staging specs were run against a local full stack (Postgres + migrations + uvicorn + Vite). Both pass; three bugs were found and fixed (bugs file). No item is `verified working (staging)` yet — every row below is honest about that.

## Every item (rule 16 vocabulary)

| Item | State | Proof |
| --- | --- | --- |
| P1-1 | fixed and tested | 18 engine goldens pass, also with the Postgres fixture; engine file untouched (71944e3). |
| P1-2 | fixed and tested | migration 0065 + models; parity 3/3 + audit hardening 1/1 on Postgres; seeds confirmed on the local e2e DB (2 locations, 16 rate-card cells) (145a5af). |
| P1-3 | fixed and tested | Client A golden to the cent through HTTP (pytest) and through the real local API over Playwright (`s22-p1-contract.spec.ts`, 4.7 s). |
| P1-4 | fixed and tested | 24 routes; 16/16 pytest; permissions × 7 roles; engine-verbatim 422s; D1–D8 recorded. |
| P1-5 | fixed and tested | contract spec passes locally with run-tag teardown (0 tagged rows after). **Staging run pending the apply.** |
| P1-6 | fixed and tested | CSV importer pytest (workbook headers) + grid entry point. |
| P2-1 | fixed and tested | grid exercised end to end locally: five people added through the draft row, Leaves, Re-hire, start edited in a yellow cell (P2-6 spec); vitest 11/11. |
| P2-2 | fixed and tested | Forecast tab seen live: 8 months, people 5→4 in the gap month, Labour + burden, GM rows; tables now named (bug #2). |
| P2-3 | fixed and tested | Setup & costs PATCH per field; costs add/edit/remove; vitest + pytest. |
| P2-4 | fixed and tested | new engagement created through the real form with "+ New client…" (P2-6 spec); from-deal pre-fill + deal-page button (vitest). |
| P2-5 | fixed and tested | Settings → Forecast calendar: burden edited and saved through the real page; the engagement's cost moved; calendar restored by teardown (P2-6 spec). |
| P2-6 | fixed and tested | owner path passes locally end to end (36–38 s), rule-18 assertions incl. the named breadcrumb. **Staging run pending the apply.** |
| P3-1 | fixed and tested | portfolio page (vitest); server totals; CSV export. |
| P3-2 | fixed and tested | cards == lists (pytest); Below-floor card filters the table (vitest). |
| P3-3 | fixed and tested | names only in roll-offs/bench (pytest + vitest); roll-off rows carry the engagement name. |
| P3-4 | fixed and tested | `worker.portfolio_scheduler.process_renewals` 4 pytests (D8 boundary); Terraform family in the saved plan, **not applied**. |
| P3-5 | fixed and tested | `process_nightly_digest` 2 pytests; EventBridge rule in the saved plan, **not applied**. |
| P3-6 | fixed and tested | three-way reconciliation + CSV pytest; Export CSV button. |

Nothing is `missing`, `blocked` or `deferred` on the code side. Every row's remaining step is the same one: the staging deploy that needs the apply approval.

## Bugs (docs/bugs/s22.md)

| # | Status |
| --- | --- |
| 1 · breadcrumb showed the engagement UUID | fixed 28b6c3f, spec asserts names only |
| 2 · Forecast-tab tables unnamed | fixed cf16a79 |
| 3 · local dev identity had no roles (never affected deployed builds) | fixed cf16a79 |

Environment artefacts noted, not bugs: `test_auth` needs the gitignored `api/dev.db`; `test_approval_concurrency` needs a disposable Postgres (both green once the environment matched CI).

## Test evidence (this phase)

| Suite | Result |
| --- | --- |
| `api/tests/test_s22_portfolio_forecast.py` + `test_s22_portfolio_scheduler.py` | 22 passed (SQLite and fresh Postgres) |
| `api/tests/forecast` | 18 passed |
| full `api` suite | green (see phase-1 report for the two environment artefacts) |
| `web` tsc | clean |
| `web` vitest (full) | see `docs/reports/s22/deploy.md` log line |
| Playwright `specs/s22/*` local | 2 passed |
| `terraform validate` / `fmt -check` | clean |

## Exact resume (after Kanna approves the plan)

```
cd /Users/srikanthparimi/OfficeApp/dealgate-s22 && env AWS_PROFILE=lm-arbiter-poc AWS_REGION=us-east-2 terraform -chdir=infra-tf apply /tmp/s22-520f5174.tfplan
```
then the migration gate, API stable on the digest, `aws s3 sync web/dist/` with cache headers + CloudFront invalidation, `scripts/deploy-smoke.sh`, the two S22 specs with `E2E_BASE_URL=https://app.dealgateapp.com`, `scripts/check-test-data-clean.sh`, scoreboard flips to `verified working (staging)`, then Kanna's click-through. No merge to main before that click.
