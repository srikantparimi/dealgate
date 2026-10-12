# S22 · Portfolio & Forecast — Phase 2 report (TEST AND FIX) — final

**Session:** S22-1 · **Branch:** `feat/s22` (worktree `/Users/srikanthparimi/OfficeApp/dealgate-s22`), pushed ·
**Staging now:** API `officeapp-dev-api:98` on image `s22-6259cda5` (`sha256:226582e71a86c67db607c848804dd11e8eaa1f687822e1a84b0a49e701863bfd`), SPA `assets/index-Lv6YxA3F.js`, all ten worker families + `api-migrate` on the same image, `officeapp-dev-portfolio-scheduler` rule ENABLED `cron(0 6 * * ? *)` ·
**Written:** 2026-10-12 · companions: `deploy.md` (every apply, task, digest, checksum), `docs/bugs/s22.md` (bugs #1–#6, all fixed), `phase1-report.md`.

## Two rounds

| Round | Image | What happened |
| --- | --- | --- |
| 1 | `s22-520f5174` | Kanna approved the saved plan (14/13/11). Migration task exit 0, API rev 97 stable, smoke `20261012T175338Z` GREEN, SPA published, both S22 specs passed on staging (55.8 s). A token-based count then found **2 engagements + 10 tagged people** left behind while the clients-only gate read clean (bug #4: the e2e bot is a test identity under the S21 runtime isolation and could not delete a client it had created through the new `POST /clients`). Cleaned through the app's deletion service as the bot (one-off task on the deployed image, audited) + `DELETE /resources`. |
| 2 | `s22-6259cda5` | Fixes for #4 #5 #6. Kanna approved the saved plan (12/14/12, image-only). Migration task exit 0, API rev 98 stable, smoke `20261012T184432Z` GREEN, SPA published, both specs passed on staging (1.4 m) in their fixture-issued form, extended gate `0 clients / 0 approvers / 0 people / 0 engagements`, bot view after: 0 engagements, 0 people, calendar restored. API proofs on staging: importer (P1-6), roll-off + bench names and card==list (P3-2/P3-3), one portfolio-scheduler tick (exit 0). |

## Every item (rule 16 vocabulary)

| Item | State | Proof (staging unless noted) |
| --- | --- | --- |
| P1-1 | verified working (staging) | deployed engine reproduces the Client A golden to the cent (`s22-p1-contract.spec.ts`, round 2); 18 goldens pass locally, engine file unmodified |
| P1-2 | verified working (staging) | migration 0065 applied by the Terraform-owned task (round 1 + idempotent round 2, exit 0); seeds read back from `GET /settings/forecast`; parity + audit hardening green locally |
| P1-3 | verified working (staging) | contract spec: totals, 12 month×assignment rows, per-row totals to the cent |
| P1-4 | verified working (staging) | every contract route exercised on staging by the specs and API proofs; 17/17 pytest incl. permissions × 7 roles + runtime isolation; deviations D1–D8 |
| P1-5 | verified working (staging) | contract spec passed on staging twice; fixture-issued client; teardown clean; gate 0/0/0/0 |
| P1-6 | verified working (staging) | `POST /allocations/import` with the workbook's headers on staging: created 5; hours 3660 / labour 178984.00 / burden 31528.72 == golden; torn down |
| P2-1 | verified working (staging) | owner path on staging: five people via the draft row, Leaves, Re-hire, yellow-cell edit, named breadcrumb |
| P2-2 | verified working (staging) | owner path: Forecast tab, "Monthly view required", gap month blank for the leaver, assignment block |
| P2-3 | verified working (staging) | owner path: Setup & costs pre-filled, type-driven greying, cost added, totals line |
| P2-4 | fixed and tested | page + "+ New client…" proven (staging through the fixture client; "+ New client…" locally and in vitest, because test identities must not create unscoped clients). **"Create engagement from deal" pre-fill is proven by vitest only**: staging has no Closed-Won fixture deal and a real deal cannot be torn down — needs Kanna's click on a real Closed-Won deal |
| P2-5 | verified working (staging) | owner path: burden +10 pts saved on the Settings page moved the engagement's cost; calendar restored afterwards |
| P2-6 | verified working (staging) | `s22-p2-owner-path.spec.ts` passed on staging in round 2 (full path incl. Setup & costs and Portfolio page) |
| P3-1 | verified working (staging) | owner path: portfolio row, URL filters, server totals row, Export CSV; CSV via API carries the totals row |
| P3-2 | verified working (staging) | four cards rendered; API proof: each card equals its list (roll-offs 1/1, bench 1/1, below floor 0/0); pytest equality |
| P3-3 | verified working (staging) | API proof: roll-off row names person, client and engagement; bench row names the person; no UUID-valued labels |
| P3-4 | fixed and tested | worker deployed (family rev 2 on the image, rule ENABLED); one-off tick on staging exit 0 with no qualifying engagement; renewal behaviour (D8 boundary, deal vs manual) proven by 4 pytests. A staging renewal needs a fixture engagement ending within two months, which would leave owner tasks behind — left for the first scheduled tick with real data |
| P3-5 | fixed and tested | same tick exit 0 (`digests=0`); once-per-owner-per-day digest proven by 2 pytests; a staging digest would email the bot owner through the outbox |
| P3-6 | verified working (staging) | reconciliation pytest green; CSV export fetched on staging with header + totals row |

Not `verified working (staging)`: P2-4 (from-deal pre-fill), P3-4, P3-5 — each with the exact remaining step above. No item is missing, blocked or deferred.

## Bugs (docs/bugs/s22.md) — all fixed

| # | Found by | Fix |
| --- | --- | --- |
| 1 breadcrumb showed the engagement UUID | local rehearsal | 28b6c3f; spec asserts names only |
| 2 Forecast-tab tables unnamed | local rehearsal | cf16a79 |
| 3 role-less local identity (never affected deployed builds) | local rehearsal | cf16a79 |
| 4 staging leak: test identity outside the S21 runtime scope | staging round 1 | 6259cda5 — scope on every forecast endpoint, test identities refused on `POST /clients`, fixture-issued spec clients, gate counts people + engagements |
| 5 `/dev/purge-client` 500 (pre-existing ImportError) | staging cleanup | 6259cda5 |
| 6 `GET /clients/forecast-options` shadowed by `GET /clients/{client_id}` | local curl | 6259cda5 → `GET /portfolio/clients` |

## Test evidence

| Suite | Result |
| --- | --- |
| full `api` suite from `api/`, fresh Postgres | exit 0, no failures (the earlier two `test_auth` failures were the repo-root working directory resolving an empty stray `dev.db`; CI runs from `api/`) |
| `api/tests/test_s22_*` + fixture-access + dev-seed | 38 passed |
| `api/tests/forecast` | 18 passed |
| `web` vitest | 89 files / 551 tests; `tsc --noEmit` clean |
| Playwright `specs/s22/*` | local 2 passed; staging round 1 2 passed; staging round 2 2 passed |
| `scripts/deploy-smoke.sh` | GREEN both rounds |
| `scripts/check-test-data-clean.sh` (extended) | clean after every staging run |

## Next

Kanna's click-through on staging (`https://app.dealgateapp.com/portfolio`, `/engagements/new`, `/settings/forecast`); the from-deal button on a real Closed-Won deal is the one path only a human can safely try. No merge to main before that click. Merge = squash `feat/s22` → `main`, then the post-merge main-image redeploy as usual.
