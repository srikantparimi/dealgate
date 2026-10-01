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
