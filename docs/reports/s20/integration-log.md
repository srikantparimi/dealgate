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

## Cycle 1 all-hands · 2026-09-30 07:45–08:20 UTC · six workers returned session-limited

**Overall result:** all six code-workers returned with "You've hit your
session limit · resets 1:40am (America/Los_Angeles)". Token usage per
worker was 1916–3661 (of a much larger nominal budget), which suggests
the limit is shared across the parent + all agents at the account level
rather than allocated per spawn. W1 and W2 each committed one substantive
commit before hitting the wall; W3, W4, W6, W7 had substantial
uncommitted WIP.

**Lead actions:**

1. **Salvaged WIP** — committed every worker's uncommitted `git status`
   as `S20 <Wn> · session-limit salvage` on their respective branches.
   Renamed W7's migration `20260930_0042_s20_w7.py` → `_0043_` to avoid
   multi-head with W6's `20260930_0042_s20_tracking.py`.
2. **Serial merge into `integrate/s20`:**
   - `a1895e4` — W1 (data truth + sync). Conflict: `requests.md` union.
   - Lead cycle-1a bookkeeping commit already at `91cdb9c`.
   - W6 (tracking features) merged clean.
   - `1f5653d` — W7 (approval-to-delivery). Conflicts: `models/__init__.py` (both DealComment + DeliveryAcceptance kept), `requests.md` union.
   - `66e7a17` — W2 (Pipeline). Conflict: `requests.md` union.
   - `dc50fbd` — W3 (SOW workflow). Conflicts: `decisions.md` + `requests.md` union, `SignatureTab.tsx` prefer W3 side (their scope per contracts §6).
   - `4bfd9d4` — W4 (reports + runbook). Conflict: `main.py` imports (both `reports` + `saved_views` kept).
3. **Verified api boots** at cycle end: `from app.main import app; len(app.routes) == 47`.
4. **Applied D1 model relaxation** (`sow.opportunity_id.unique = False`) as Lead-owned per contracts §6 — W3's rollup tests required it. Alembic migration owed for Postgres (`sow_rollup` requests block in `requests.md`).
5. **Fixed two W3 test-fixture bugs** (`User(...)` missing `name=`).
6. **Commit `9a2ebc2`** captures both fixes.
7. **Pushed `origin/integrate/s20`** at `9a2ebc2`.

**Regression state after all cycle-1 merges + Lead fixes:**

| Suite | Status | Notes |
| --- | --- | --- |
| `test_sow_rollup.py` (7 tests) | passing after D1 relaxation + fixture fix | Requires alembic revision for Postgres |
| `test_deletion_by_state.py` (6 tests) | passing after fixture fix | D6 correctness proved |
| `test_sow_upload_binding.py::test_upload_with_both_bound_creates_sow_under_deal` | **failing** | W3 cycle 2. Two other cases in the file pass |
| `test_delete_everywhere.py::test_delete_sow_removes_it_from_every_list` | **failing** | Test asserts pre-D6 behavior; must be updated to use `archive_sow` |

**Cycle-2 spawn: not attempted** — same session-token cap that killed
cycle 1 remains in effect; a fresh spawn would land in the same wall.

**Cycle-1a request routing update:**

| Request | Landed? |
| --- | --- |
| W5-01 · `_PREFIX_RE` extension | **not landed.** Owner W1 was interrupted before touching `worker/e2e_cleanup.py`. Follow-up owed. |
| W5-02 · TF Cognito approvers | deferred to a dedicated TF slice per D-COG-01. T27 + T44 stay xfail. |
| W5-03 · `/api/dev/mirror/opportunities/{id}` | **not landed.** |
| W5-04 · pipeline export CSV | **not landed.** |
| W1-...-01 · sync_status watermark migration | **model change landed on W1's commit; alembic revision owed for Postgres.** |
| W3-...-01 · relax `sow.opportunity_id` uniqueness | **model change applied by Lead at `9a2ebc2`; alembic revision owed for Postgres.** |
| W7-...-01 · new migrations for `delivery_acceptance` + `project` | present in `alembic/versions/20260930_0043_s20_w7.py`. Not yet run on staging. |

**Deploy state:** see `deploy.md`. Not executed tonight. Runbook ready
at `docs/runbooks/deploy.md`.
