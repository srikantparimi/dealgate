# S21 Release Progress

Status: implementation in progress, NOT ready for staging click-through or merge.

- Source baseline: 321b365393171837ccfe364def2b13ae5a72c06d; separate feat/s21-forecast worktree.
- Scope: [51 requirements](scoreboard.md), [45 scenario definitions](acceptance.md), [65 historical S20 rows](s20-carryover.md).
- S20: merge/tag verified; final main-image rollout unproved; check-only smoke failed extraction on API rev70. [Evidence](baseline.md).
- S21: trusted fixture boundary increment and independent QA corrections integrated through bd22cb7. 130 targeted tests pass locally; complete requirements remain missing. No new feature is staging verified.
- Forecast: immutable calendar quantity engine integrated at e041387; independent A/B arithmetic checks pass. No persisted Forecast views, complete pricing registry or new deployed Forecast functionality yet.
- Operations: [SES sandbox confirmed; real recipients not covered; consumer/monitoring/approval/canary outstanding](operations.md).
- Migrations/cleanup: no migration, data backfill or broad cleanup performed. Only this baseline smoke's owned client was deleted by its existing teardown.
- Deployments: no new image or Terraform mutation made. Existing deployment is not relabelled as S21.

Local verification: first full suite 1005 passed / 4 failed / 6 skipped / 150 pre-existing xfailed. Four failures repaired and covered by the final 130-pass targeted run; full combined rerun still pending. Independent QA's original 9-pass/4-fail report is preserved; unchanged recheck on bd22cb7 passed 13/13. Real Postgres migration/audit checks are separate evidence, not a staging claim. Details and exact resume commands: [handoff](handoff.md), [increments](implementation-log.md).

Checkpoint S21F-01 honors the repository 60-minute hard stop. Full scope remains 70-100 engineering hours plus external waits; no scope dropped. All 51 item states and dependencies remain in scoreboard.md; all 45 scenarios remain in acceptance.md. No requirement is complete just because one increment passed.

Rollback: no shared runtime change yet. Future additive migrations require restore rehearsal; no deleting business records for rollback. Staging gate and human acceptance precede any main merge; approved main still needs its own image/digest/smoke verification.
