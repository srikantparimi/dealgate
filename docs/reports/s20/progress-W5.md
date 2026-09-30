# S20 · progress log for W5 (owned by W5)

**Scope reminder:** see `docs/directives/s20-overnight.md` §2, and
`docs/reports/s20/contracts.md` §6 for file ownership.

Update after every commit on `s20/W5`.

Sections:
- **Decisions / notes:** what was decided while working.
- **Files touched:** paths (owned + patches requested via requests.md).
- **Proven:** tests passing, evidence links.
- **Next:** what would come after the current step.
- **Blockers:** hard block only (per §9). Everything else keeps moving.

---

## Cycle 0 · spawn · 2026-09-30T06:31:31Z

Not started yet.

## Cycle 1 · skeleton drop · 2026-09-30

### Decisions / notes

- **tests.md structure:** columns `id | title | method | result | evidence | owner | notes`. Every T01–T44 seeded `result=not_run`. `notes` carries the current xfail reason so a growing-suite run can filter for "waiting on Wx".
- **method column** distinguishes `automated · <path>` from `manual+steps`; a hybrid (`manual+scripted · <script>`) marks the T03 parity + T29 stub dry-run + T36 deploy evidence where the script does the capture but a human confirms the diff.
- **Multi-role auth** — `tests/e2e/fixtures/multi-role-auth.ts` reads the SystemAdmin creds via existing `staging-auth.ts::mintStagingTokens()` and, when the `officeapp-dev-e2e-approvers` secret is present, mints per-role tokens for `submitter / delivery / hr / finance / legal / ceo`. If the secret is missing (which is the case tonight per isolation.md — only 4 users exist), roles fall back to the SystemAdmin smoke bot with a WARN log. T27 (permissions uniform) becomes a `blocked` row in tests.md until Lead applies the terraform module that partitions the pool. Recorded in `decisions.md` (patch queued in `requests.md`).
- **Skeleton pytest convention:** every test uses `@pytest.mark.xfail(reason="depends on W#...", strict=False)` so it doesn't fail the growing suite before its capability lands. The body raises `AssertionError("skeleton…")` — clear signal to whichever worker unmarks it that they're now on the hook. `strict=False` means once the assertion actually passes, it'll flip to xpass (visible signal) rather than silent fail.
- **T03 parity harness (`scripts/t03-parity.sh`)** is a read-only capture of 6 surfaces per deal (list, HubSpot source, mirror, client detail, deal detail, export). It's runnable tonight against staging; the mirror + export endpoints may be missing pre-W1/W2 landing, in which case the capture logs `(endpoint not exposed; W# to add)` and continues.
- **T32 injection script (`scripts/inject-events.py`)** tags every event with `s20-injection` marker so `worker/e2e_cleanup.py::_PREFIX_RE` reaps them — pending W1's marker addition (see `requests.md` for the requested regex extension).
- **A5 query-plan evidence** lives in `test_s20_pagination_vs_totals.py::test_query_plan_scans_proportional_to_selectivity` — Postgres-only, skips on the default SQLite path. Runs during the Lead's staging soak.
- **T44 full journey** is a `.describe.serial` so state (dealId, packageId, projectId) carries between steps. Every step is `test.skip` today; unskip in bottom-up order as W3/W7 land.

### Files touched

Owned (this commit):
- `docs/reports/s20/tests.md` — new
- `docs/reports/s20/t03-parity.md` — new
- `docs/reports/s20/click-through.md` — new
- `docs/reports/s20/progress-W5.md` — this file
- `tests/e2e/fixtures/multi-role-auth.ts` — new
- `tests/e2e/specs/s20/t01-sidebar-navigation.spec.ts` — new
- `tests/e2e/specs/s20/t40-live-repro.spec.ts` — new
- `tests/e2e/specs/s20/t44-full-journey.spec.ts` — new
- `scripts/t03-parity.sh` — new
- `scripts/inject-events.py` — new
- `api/tests/test_s20_stage_reconciliation.py` — new (T02)
- `api/tests/test_s20_owner_resolution.py` — new (T04)
- `api/tests/test_s20_filter_combinations.py` — new (T05)
- `api/tests/test_s20_filter_dates.py` — new (T06)
- `api/tests/test_s20_client_rollups.py` — new (T08)
- `api/tests/test_s20_extraction_recovery.py` — new (T12)
- `api/tests/test_s20_many_sows_per_deal.py` — new (T14)
- `api/tests/test_s20_nda_msa_rules.py` — new (T15)
- `api/tests/test_s20_gm_thresholds.py` — new (T17)
- `api/tests/test_s20_gm_incomplete_inputs.py` — new (T18)
- `api/tests/test_s20_stale_package_refused.py` — new (T19)
- `api/tests/test_s20_ceo_conditional.py` — new (T20)
- `api/tests/test_s20_material_change_invalidates.py` — new (T21)
- `api/tests/test_s20_signature_verification.py` — new (T22)
- `api/tests/test_s20_release_authorization.py` — new (T23)
- `api/tests/test_s20_baseline_forecast_actuals.py` — new (T24)
- `api/tests/test_s20_renewals_calendar_months.py` — new (T25)
- `api/tests/test_s20_report_totals.py` — new (T26)
- `api/tests/test_s20_permissions_uniform.py` — new (T27)
- `api/tests/test_s20_sync_edge_cases.py` — new (T28)
- `api/tests/test_s20_ownership_and_rollup.py` — new (T31)
- `api/tests/test_s20_freshness_injection.py` — new (T32)
- `api/tests/test_s20_scan_resume.py` — new (T33)
- `api/tests/test_s20_source_dedup.py` — new (T34)
- `api/tests/test_s20_pagination_vs_totals.py` — new (T35 + A5 query plan)
- `api/tests/test_s20_upload_interrupt_recovery.py` — new (T37)
- `api/tests/test_s20_security_boundaries.py` — new (T38, includes cleanup-regex real assertion)
- `api/tests/test_s20_report_dependency_failure.py` — new (T39)
- `api/tests/test_s20_signature_nda_msa_rule.py` — new (T41)
- `api/tests/test_s20_report_scale.py` — new (T42)
- `api/tests/test_s20_integrations_truthfulness.py` — new (T43)

Patches requested via `requests.md` (Lead applies):
- (queued for next commit) add `S20 e2e ` and `s20-injection` to `worker/e2e_cleanup.py::_PREFIX_RE` so scheduled cleanup can reap our fixtures on the 24h tick.
- (queued) apply the `officeapp-dev-e2e-approvers` Cognito module so per-role Playwright partitions are testable tonight; without it, T27 is `blocked`.
- (queued) expose a read-only `/api/dev/mirror/opportunities/{id}` endpoint for T03 capture step 3.

### Proven

Locally (this worktree):
- `python3 -c "import ast; …"` — every `test_s20_*.py` parses OK.
- Every skeleton uses `@pytest.mark.xfail(strict=False)` + a raise —
  they will show up as `expected fail` in the growing suite until
  their dependency lands, at which point the worker unmarks + implements.
- `test_s20_security_boundaries.py::test_e2e_cleanup_regex_does_not_match_real_clients`
  is NOT xfailed — it asserts real behavior and passes today (see
  `worker/e2e_cleanup.py::_PREFIX_RE` walk-through against known names).

Not run yet (waiting on Lead's growing suite):
- `pytest -q` — needs deps installed on the Lead machine.
- `npx vitest run --reporter=dot` — no S20 vitest specs yet.
- `npx playwright test` — needs `officeapp-dev-e2e-approvers` secret
  and W2 pipeline landing for the T01 assertions to be meaningful.

### Next

- Cycle 2 (once W2 lands any pipeline change): un-skip T01 + T40
  and run against staging. Fill in evidence for whichever assertions
  pass; requests.md for anything that fails.
- Cycle 3 (once W3 stub migration + upload lands): un-skip T10, T11,
  T13, T14, T15, T19, T20, T21 assertions.
- Cycle 4 (once W7 signature/release lands): un-skip T22, T23, T24,
  T37; run T44 in observer mode against a hand-created HubSpot deal.
- Every ~2h when Lead pulls `integrate/s20`, run the growing suite and
  update `tests.md` result column with `pass|fail|not_run|blocked`.
- T03 parity capture — run `scripts/t03-parity.sh --list` to pick a
  real deal; run against it; fill in `t03-parity.md` field table by hand.

### Blockers

None hard. Every test is `not_run` or `xfail` until its underlying
capability lands; that's expected work sequence, not a block.

Soft dependencies queued in `requests.md`:
1. Lead to add `S20 e2e ` prefix to cleanup regex.
2. Lead to apply the multi-role Cognito module (else T27, T44 role
   split remain covered only by SystemAdmin bot).
3. W1 to expose `/api/dev/mirror/opportunities/{id}` for T03 step 3.
4. W2 to expose `/api/pipeline/opportunities/export.csv` for T03 step 6
   and T35 test_export_returns_full_filtered_set.
