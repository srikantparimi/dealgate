# T02 Workspace Navigation: Local Connected Pass

Current affected regression: applicationa5ee76d9622a8b0008b867cb7c4361a4ca78f6b7,
session27216 passed1/30.5s, test26.7s on2026-10-02 23:02UTC. Same original
assertions, after shared SOW route guard. Screenshot updated by this run.
Output tests/e2e/test-results/s21-t02-after-t05-ready.
Historical attempt88040 failed before fixture creation with ECONNREFUSED while
restored API started. Confirmed startup and /me200 before rerunning unchanged.

2026-10-02. Application HEAD `39f157505c2904dd8e75a86c5f8d3b0e4eb8cc0b`
(application code unchanged from941953a); test authored in working tree and
committed with this evidence. Session37810 exit0: **1 passed (38.5s)**,
test33.5s, no retries/skips or application changes.

From `tests/e2e`:
```sh
npx playwright test --config playwright.s21-local.config.ts s21-workspace-navigation.spec.ts --workers=1 --output=test-results/s21-t02-39f1575
```

All original conditions verified locally:
- T02.01: Overview -> Staffing & GM -> Approvals -> browser Back to Staffing
  -> Back to Overview. Every URL and selected tab asserted.
- T02.02: SOW heading and all three relevant tabs visible at every stop.
- T02.03: Same version label and exact authoritative current version ID at every
  stop. Full version response unchanged after the journey.
- T02.04: Exactly one visible Readiness region at every stop.
- T02.05: Direct Approvals deep-link and page reload preserve the selected tab
  and the same shell/identity/readiness assertions.

[Inspected screenshot](t02-workspace.png) shows the final Approvals view.
Real Vite5210/API8210/PostgreSQL `s21_journey`0061; unique local test actor.
The declared synthetic SOW uses the existing guarded
`scripts/s21_conflict_review_journey.py`, not a fake feature response or claimed
extractor result. No cloud storage objects were created. Issued local fixture
rows remain retained under their expiry/provenance controls.

This proves the original T02 desktop navigation sequence, not T26's full
keyboard/mobile/accessibility matrix or production Cognito/staging behavior.
S21-02/DG-06 retain their other conditions and release gates.
