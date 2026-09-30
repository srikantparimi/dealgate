# S20 · integration log (Lead-owned)

Every ~2-hour integration cycle appends here. Each entry:

- Cycle number + UTC timestamp.
- Branches merged (SHAs).
- Conflicts + resolution (against `contracts.md` + tests, not by
  precedence of branch or surface).
- Regression + gate results (pytest, vitest, deploy-smoke, single-
  query-service, test-data-clean).
- Deploy result (image tag, task-def revs, migration exit, service
  stability, SPA invalidation).
- W5 growing-suite result.
- Red / green + what corrective commits (if any) followed.

---

## Cycle 0 · 2026-09-30 05:10 UTC · pre-worker baseline

- Starting point: `integrate/s20` @ `<sha-at-Hour-0>` — matches
  origin/main + review + directive.
- Baseline pytest: 832 passed / 6 skipped (from S19 slice 1 merge).
- Baseline vitest: 266 passed.
- Baseline deploy-smoke: green on 2026-09-30 04:32 UTC (see
  `docs/reports/s19-1/smoke-postmerge.txt`).
- No worker commits yet.

Ready to spawn W1–W7.

## Cycle 1a · 2026-09-30 05:20 UTC · W5 merged

- Branches merged: `origin/s20/W5` @ `423eeb0` → `integrate/s20` @ `5852098`.
- Conflicts: none. W5 owns `tests/**`, `scripts/**` (non-deploy), `docs/reports/s20/tests.md, click-through.md, t03-parity.md`. All new files.
- Regression: `pytest tests/test_s20_security_boundaries.py` → **1 passed, 8 xfailed**. The one live assertion (`test_e2e_cleanup_regex_does_not_match_real_clients`) protects real staging clients from the e2e cleanup regex. The 8 xfails are seeded skeletons that flip to real assertions when W1/W2/W3/W4 land.
- No vitest run (no web changes in W5).
- No deploy this cycle (harness only; no runtime code delta).
- W5 filed four requests in `requests.md` — routed below.

### Cycle-1a request routing

| # | Owner | Route action |
| --- | --- | --- |
| W5-01 · S20 fixture prefixes in `_PREFIX_RE` | W1 | Pending W1's cycle-2 pickup (or Lead applies at cycle 2 if W1 hasn't touched `worker/e2e_cleanup.py`). |
| W5-02 · TF Cognito approvers partition | Lead | **Deferred to a controlled TF slice.** See `decisions.md` D-COG-01. T27 + T44 stay xfail with the reason: multi-role users don't exist tonight. Not a hard block — `multi-role-auth.ts` falls back to the smoke bot with a WARN, and the harness runs. |
| W5-03 · `GET /api/dev/mirror/opportunities/{id}` | W1 | Pending W1's cycle-1 push (W1 still running). |
| W5-04 · `GET /api/pipeline/opportunities/export.csv` | W2 | Pending W2's cycle-1 push (W2 still running). |

Workers still in flight: W1, W2, W3, W4, W6, W7. Lead continues waiting.
