# S20 close-out — what is actually left, and what "done" means for each item

Prepared for Kanna Parimi, 2026-10-01 evening. Source of every line: the agent session reports pasted into this conversation (S20 Sessions 1–5, Lead C1/C2, S21-1 through S21-1d) and the "Remaining work" table of `docs/releases/s20.md` as posted verbatim by the S21-1d session. Nothing here is inferred from code I have read; I have not read the repo. Where I am unsure, the line says so.

## Current state of the repo (as of the last report)

| | Value |
| --- | --- |
| `main` | `8b5100c` — the S19 slice-1 merge. **Nothing from S20 is on main.** |
| `integrate/s20` | `14c6af9` — 65 commits ahead of main |
| Staging (app.dealgateapp.com) | rev 67, image `s20-9b7bc5d9`, deployed from `integrate/s20 @ 14c6af9`; smoke green |
| Last action | S21-1d stopped before merging: full Playwright on rev 67 = 56 passed · 30 skipped · **25 failed** · 8 did not run. Pytest 994 passed · 0 failed. A fix prompt was issued; I do not know whether it ran. |
| Scoreboard | `docs/reports/s20/scoreboard.md` — last posted totals (S20 + S21 rows together): 36 verified · 11 fixed+tested · 5 missing · 2 blocked · 11 deferred · 65 total. S20-only totals are not separately posted; Codex must compute them from the file. |

## Step 0 for Codex — reconcile before doing anything

Read `docs/reports/s20/scoreboard.md`, `docs/releases/s20.md`, `docs/reports/s20/tests.md`, `docs/reports/s20/decisions.md` and `CLAUDE.md` (rules 12–19). Produce the S20-only list of rows whose state is not "verified working (staging)", with the row id, state and the proof column as they are in the file. Compare with the table below. Where they disagree, **the repo wins** — report the difference, do not edit this document to match. Budget for step 0: 15 minutes, report only.

## A. Items blocking the merge to main (do these first, in order)

| # | Item | What was reported | What "done" means |
| --- | --- | --- | --- |
| A1 | Watching card hides at zero | `s20/t39-w4-session5.spec.ts:33` fails on staging with an empty watchlist: `CommandCenter.tsx` lines ~637–657 do not render the card when `watchingCount` is 0. Fails on isolated rerun, so not a flake. Scoreboard row W6-7 says "verified working (staging)" — that is now wrong. | Card renders "0" on an empty watchlist and the real count otherwise; t39:33 passes on both; W6-7 proof updated to the new rev. |
| A2 | 22 legacy Playwright specs cannot run against staging | `tests/e2e/specs/01-*.spec.ts` … `25-*.spec.ts` (everything outside `s20/`) use `seedClientWithDeal()` and the `X-Test-User` header, which exist only on the local dev server (`.github/workflows/e2e.yml` spins up Postgres + uvicorn + Vite). Against `https://app.dealgateapp.com` they fail by construction. Nothing in `playwright.config.ts` or `tests.md` says so. | `playwright.config.ts` runs them only when `E2E_BASE_URL` is a local dev server and skips them against staging with the reason "dev-harness only"; `tests.md` records this. These are not failures being hidden — they were never staging tests. |
| A3 | Two S20 specs flaky under full-suite load | `s20/t09-names-not-ids.spec.ts:43` (deal column) and `s20/t40-live-repro.spec.ts:92` (L05 client rows) fail in the full serial run and pass on isolated rerun. | Recorded in `tests.md` as known flakes with the item they wait on (S21-12 raw ids, S21-9 pipeline client view). No retry logic added. If a root cause is found in under 20 minutes, fix it; otherwise record and move on. |
| A4 | Full Playwright must be green on the merge rev | After A1–A3: deploy via D5 (`scripts/deploy-smoke.sh`, the same path as revs 53–67), run full Playwright serial and full pytest against the new rev. | 0 failed. Every skip or xfail carries a linked item number in `tests.md`. |
| A5 | Merge | Squash-merge `integrate/s20` → `main`, commit body = `docs/releases/s20.md` (fix its "rev 66" reference to the actual merge rev first). Tag `s20-release`. The push-to-main workflow (`.github/workflows/deploy.yml`) builds a **new** image tagged with the merge SHA — same source tree, different tag. That is expected (recorded as D-S20-D5b, or record it now if the S21-1d session did not). `gh` is not logged in from the agent environment; do not use it. | Poll AWS read-only (describe the api service) until its task definition runs the image tagged with main's SHA and the service is stable (max 25 min); run `scripts/deploy-smoke.sh` check-only against app.dealgateapp.com; smoke green. Delete `feat/s20-w4` and `feat/s20-w7`. Keep `integrate/s20`. Post main's commit, image tag, smoke result. |

Estimated: one session of ~75 minutes including the deploy and the post-merge wait.

## B. S20 rows not proven on staging (agent work, after the merge, on branches off main)

| Row | Reported state | What was reported | What "done" means |
| --- | --- | --- | --- |
| W7-1 … W7-5 (signature verification, release, delivery acceptance, project creation, forecast vs actuals) | fixed and tested (unit) | Code landed in Lane B session (`feat/s20-w7 @ 8b42c81`, merged). Pytest green. **Never exercised end to end on staging.** `tests/e2e/specs/s20/t44-full-journey.spec.ts` is a skip skeleton. The W7 flow needs no HubSpot write (the earlier claim that it needed a writable token was wrong); it needs a signed-SOW fixture — a fixture SOW PDF plus a signed copy whose signatories match the approved version — which does not exist yet. The release note lists t44 under "deferred by design" while also saying W7 rows need it to flip; that is a contradiction. | Build the fixture under `tests/fixtures/sow/` (no real client data). Write t44 for real: upload → confirm → approve via e2e approvers → signed upload → signature verified → release → delivery acceptance → project on Projects with names → one month of actuals → forecast vs actual GM; run under the e2e run tag; teardown; leak gate 0. Flip W7-1..5 only on a staging pass. One session. |
| W6-8 (a deal in several groups counts once) | fixed and tested (unit) | Unit test `test_deal_in_multiple_groups_counts_once` proves the invariant. The staging assertion written in S4b checks only that the paginator total parses on an empty watchlist — it proves nothing about counting once. | Seed via the e2e run-tag path: one watched deal in three groups; Command center "Watching" count and `/pipeline?watching=true` total both equal 1; teardown. Small; can ride with t44. |
| W4-1 "SOWs in progress" card scope | verified working (staging) per scoreboard, but Lead C2 reported "deep-link ≡ card for 2/3 cards" | The card counts approval packages pending across three lanes; its deep-link `?attention=pending_approval` filters opportunities by an attribute flag. Different scope, so the number on the card and the count on the list it opens can differ. | Product decision (Kanna, already given): the card counts SOW packages in review and links to SOW approvals filtered to in-review, not to Pipeline; card number == list count; test per card. Small. |
| FINAL-T38 (security boundaries + production-claim honesty) | fixed and tested | Needs a full-suite run recorded against the final rev. | Flips automatically once A4 is recorded in `tests.md` with the rev. Verify it was flipped; no new work expected. |
| W1-A2 / A3 / A4 / T28 (continuous consumer with measured freshness; backfill scan generation + resume; source-event dedupe with atomic commit; T28 stage-rename/association xfails) | fixed and tested (unit) | Backend code landed in W1. The continuous consumer's Terraform resources (SQS consumer worker, ~30 resources) were **deliberately not applied** in Session 2 because the Terraform state had not converged after the drift incident (decision S2-D). The nightly reconcile and webhook intake are live; the continuous consumer is not. The sync works today without it; what is missing is the "fresh within minutes" promise and its measured lag. | This is a Terraform apply through `scripts/tf-init.sh` with the interactive prompt answered by Kanna, **after** a drift-adoption slice confirms `terraform plan` on the whole root shows only the intended adds. Then run the T28 xfails and the freshness tests on staging. This is the largest remaining S20 item and the only one with infrastructure risk. One session plus Kanna at the keyboard for the apply. If Kanna chooses to defer it, the sync still works on reconcile + webhooks; say so in the release note. |
| T32, T34 | unknown | Earlier S20 totals listed "3 missing (T32–T34)". The release-note table names only T33 (under deferred). I cannot tell from the reports whether T32 and T34 were verified, folded into another row, or dropped. | Codex step 0 answers this from `scoreboard.md`. |

## C. Needs Kanna, not an agent

| Row | What it is | What to do |
| --- | --- | --- |
| W1-ALARMS / W4-5 | CloudWatch freshness alarms — Terraform module written in Session 2, never applied because applying needs a human to answer the terraform prompt (rule 15). | Open a Lead session, say "run tf-init and terraform plan for the alarms module". Read the summary. If it says only adds in the alarms module, answer yes to the apply. ~10 minutes. |
| FINAL-CLICK | Product-owner click-through of the final S20 rev. | Your 10-minute check on whichever rev is on main: Pipeline shows real deals and no test rows; a SOW uploads, GM calculates, Delete removes it everywhere; Liberty Mutual shows no "E2E Staging Bot". You did most of this on rev 62; the formal pass is on the merge rev. |
| (S21-8, listed for completeness) | SES identities for the five approvers — the plan is clean (6 to add, 0 to change, 0 to destroy). | Same "answer the prompt" step as the alarms, can be done in the same sitting. Then the five people each click one verification email. This is an S21 row, not S20. |

## D. Deferred by design — not S20 work

| Row | Why |
| --- | --- |
| W1-D10 Business unit | The HubSpot portal has no Business Unit property; the app shows it as not mirrored. Nothing to build until the property exists. |
| W1-T33 | Chaos test (kill the backfill worker mid-scan and prove it resumes). A planned exercise, not a build item. |

## What I do not know

Whether the A1–A3 fix prompt from this evening ran; the current S20-only scoreboard totals; the fate of T32/T34; whether D-S20-D5b was recorded. Codex step 0 settles all four in 15 minutes.

## Rules that apply to every item above

Rule 14 (branch → staging → smoke → Kanna's click → squash merge), rule 15 (no scripted yes to terraform; `scripts/tf-init.sh` refuses with a local tfstate present), rule 16 (budget with hard stop; every item reported by number in one of the five states with proof; deploy starts at a fixed minute), rule 18 (a finding becomes a failing test first), rule 19 (heartbeat every step and every 15 minutes). After A5, every item is its own branch off `main`, merged the same day it is proven.
