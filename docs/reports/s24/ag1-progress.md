# S24-AG1 progress

**Status 2026-10-16 ~01:00 PT: T phase done, bugs fixed, deployed to staging** (API rev 120, image `s24ag1-79639659`;
migration 0072 applied on rev 119 by the Terraform migration task; SPA `index-CljtRVVQ.js`; smoke GREEN; staging specs green). The report is
`docs/reports/s24/ag1-report.md`. Not merged: Kanna clicks first. The pause notes below are kept for the record.

## Earlier: paused 2026-10-15 16:58 PT at the operator's request: network change)

Branch `feat/s24-ag1` (worktree `~/OfficeApp/dealgate-s23-pl2`), based on main `fd8dc40` (S23-PL2). Not pushed, not
merged, **not deployed**: staging is unchanged by AG1 (still rev 118, image `s23pl2main-fd8dc40f`).

## Done

| Step | State | Proof |
|---|---|---|
| Pack added, branch created, questions recorded (rule 1), blueprint:14 fixed | done | `d423ce0` |
| B1-B15 and F1-F12 code-complete | done | `b36c19c` (126 files) |
| Review findings (frontend, safety, backend) fixed, each with a test | done | `5fd8c9b`; `docs/bugs/s24-ag1.md` #91-#103 |
| Full web suite | green | 122 files, 1,004 tests, `tsc --noEmit` clean (after `5fd8c9b`) |
| S24 API suites | green | 11 S24 files pass; 1 Postgres-gated skip; ruff's 27 findings all predate AG1 |
| Staging T2/T12/D9/S4/S11 probe | written, proven locally | read-only guard confirmed; cards = drills; Pipeline card = Agreements card (12 = 12) on the local seed; override 5,845 bytes |

## In progress when paused: the T phase (T1-T14)

The T-phase workflow (`wf_353f71d2-8bb`) was stopped cleanly. No agent had finished, so nothing is cached.
Lanes T-A and T-B had started; T-C and T-D had not. Their partial, **unverified** files are left untracked in the
worktree (not committed) and copied to `~/OfficeApp/.ag1-handoff/partial-lane-files/`:

- `api/tests/test_s24_ag1_uploads.py` (T-A, T3; 11 tests written)
- `api/tests/test_s24_ag1_permissions.py` (T-A, T6; 2 tests written)
- `api/tests/test_s24_ag1_batch_t5_pg.py` (T-B, T5; 5 tests written)
- `api/tests/test_s24_ag1_shared_object_pg.py` (T-B, T4; 2 tests written)

No lane process was left running and no scratch database was left behind (only `dealgate_ag1_test`,
`dealgate_ag1_e2e` and `ag1_beb_base` exist on the local container, as before).

## Resume, in order

1. Re-run the T-phase workflow from its saved script (`~/OfficeApp/.ag1-handoff/s24-ag1-t-phase-wf_353f71d2-8bb.js`),
   telling each lane that its files may already exist from the interrupted run: read them, keep what is right,
   finish them. If `/private/tmp` was cleared, point the script's `SCRATCH` at `~/OfficeApp/.ag1-handoff/scratch`
   (it holds `tplan.md`, `plan.md`, `test_inventory.txt`, `web_test_inventory.txt`).
2. Fix the bugs the lanes log, one by one, each recorded in `docs/bugs/s24-ag1.md` with its test; remove each
   strict xfail as its bug is fixed.
3. Full API suite (Postgres-gated files with `DEALGATE_POSTGRES_URL`), full web suite; restore
   `api/tests/forecast/fixtures/` if the forecast suite rewrote them; commit.
4. Deploy exactly as PL2: buildx amd64 image `s24ag1-<sha8>`; saved Terraform plan; image-only check; show the plan
   summary; apply from the saved plan (migration 0071 → 0072 runs through `terraform_data.api_migration`);
   publish the SPA with cache headers and invalidate CloudFront; `scripts/deploy-smoke.sh`.
5. Staging: run the T2 probe (`scratch/t2/build_t2.py <tag>` → one-off task on the new API task definition), the
   B13 orphan report (`python -m worker.agreement_orphans` on the deletion-cleanup task definition), the T9 staging
   spec as the e2e bot, and the leak gate.
6. Write `docs/reports/s24/ag1-report.md`: every D, S, B, F and T item in one of the five states with proof, the
   deviations, blocked items, the leaked client and orphan findings, the two D9 name pairs and the S4 count. Do not
   merge: Kanna clicks first.
