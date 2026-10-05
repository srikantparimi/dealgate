# T05 Reviewer Planning Ownership

2026-10-02 22:35 UTC, basee0cfceef9224b25e71266c2eb4fddca1a09adb3e.
Original S21-05/T05 unchanged. Lead owns ReviewStream.tsx,
SubmitApprovalDialog.tsx (reuse one actual plan editor), focused UI test and
tests/e2e/local/s21-reviewer-plan.spec.ts. No new approval policy.
QA exposed retained-snapshot route races in the host. Lead additionally owns
SowWorkspace.tsx only for route-bound refresh/callback fencing and its regression.

Worker /root/s21_governance owns ONLY scripts/s21_reviewer_plan_fixture.py
and docs/s21/lanes/reviewer-plan-fixture.md in its dedicated branch/worktree.
Author-only until lead grants runtime. Guard fixture seed to local127.0.0.1:55421,
user s21, database s21_review_[32 hex], matching tenant. Refuse nonempty business
tables. Lead alone creates/comments/migrates/runs/drops the private database and
serially replaces/restores the owned API. Never alter retained s21_journey groups.

Fixture declares synthetic draft SOW/confirmed scope/above-floor complete GM,
no approval packages/tasks; six distinct eligible registered reviewers (Delivery
has an alternative), one nonmember/unauthorized submitter, one test admin owner.
Use real service fixture grants and group setup in the isolated database. Source
is declared, not live extraction. No uploads/storage/providers/workers required.
Print independent manifest: source version IDs, function->eligible/default IDs,
expected frozen assignments and counts; caller will use real plan/submission API.
No precreated packages or decisions and no approval service bypass.

Proof: open Approvals without earlier selections; see functions/eligible names;
change Delivery; reject bad/nonmember/submitter/duplicate reviewer IDs and
unauthorized submission with zero package/task count changes; submit once and
reload exact frozen versions, chosen assignees/task owner. T06 OOO/CEO and real
mail/Cognito/staging remain separate. One heavy runtime, up to two light workers.
