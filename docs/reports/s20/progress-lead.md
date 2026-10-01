# S20 · Lead progress log

## 2026-10-01 · C1 deploy (correction)

C1-resume-2 stopped before deploy citing a chicken-and-egg with a main
merge. **That stop reason was wrong.** `scripts/deploy-smoke.sh` deploys
`integrate/s20` directly via the manual steps in `docs/runbooks/deploy.md`
(api revs 53–62 prove it — eight prior deploys from this branch without a
main merge). The Lead runs the deploy before any main merge; the main
merge is gated **after** staging proof, not before (CLAUDE.md rule 14).
CI on `main` is post-merge redeploy only (deploy.md §0 preamble).

This checkpoint resumes from `integrate/s20 @ 0360b76` and runs the
branch-deploy path end to end.

## 2026-10-01 · Lead-C2 (steps 3–4) · deploy + verify

- **16:00 UTC · 1/7** · reading runbook + scoreboard · 0m · next: image build.
- **18:41 UTC · 2/7** · image build (s20-b75959ff, linux/amd64) backgrounded · ~2m elapsed · next: alembic + task-def register once image lands.
- N-1 state captured: api=rev64, migrate=rev2, 6 workers on rev17/15 (e2e-cleanup family not registered — carried forward from prior deploys).
- **18:48 UTC · 3/7** · build+push done (s20-b75959ff · digest 5b5981c7); api rev=65, migrate rev=3; alembic exit=0; api update-service force-new-deployment issued · 7m elapsed · next: wait services-stable then smoke.
- **18:52 UTC · 4/7** · api rev 65 stable; smoke-c2 GREEN (RUN_TAG=`smoke 20261001T184714Z`); 4-way reconcile confirmed 104/104/104/104; summary now exposes 3 new keys · 11m elapsed · next: Playwright S20 serial + 6 workers register.
- **18:58 UTC · 5/7** · Lane A probes pass (summary 3 keys, by-stage=104, CSV x-totals=104, bedrock/ses/heartbeat live); 4-way reconcile verified; Playwright at 6/40 · 17m elapsed · next: wait Playwright, then record W7-* decision.
- **W7 e2e flow decision:** t44-full-journey.spec.ts is a `test.skip` skeleton (all 10 steps skipped pending W5 un-skip + read-only HubSpot token tonight per isolation.md F1). No new 8-step spec can be authored + run in remaining budget. W7-1..W7-5 stay at `fixed and tested` with S2-W7 proof extended; staging flip deferred.
