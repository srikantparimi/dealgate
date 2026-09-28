# Directive S17: simplify NDA/MSA, allow deleting any SOW, clean staging

From: Kanna Parimi, product owner. Commit as
`docs/directives/s17-simplify-delete.md`. Same feature-branch discipline
as S16 (rule 14). Do everything yourself; ask me only for the click-through.

## 1. NDA & MSA becomes a simple document store

- Remove all agreement tracking: states (missing / requested / sent /
  executed), owners, next actions, "Obtain signed NDA/MSA" tasks, and
  agreement-gap blockers. Delete the code, not just the UI.
- The NDA & MSA page becomes: one Upload button (pick client, pick NDA
  or MSA, attach file). The list shows client, type, file name, uploaded
  by and date, plus Download and Delete. No statuses, no dates to fill
  in, no extraction.
- SOW upload form gets one checkbox: "NDA and MSA are signed with this
  client". Checked means that SOW is marked compliant and nothing else
  is asked. Unchecked is allowed and is simply shown as a note on the
  SOW, never a blocker.
- Signature and approvals no longer check agreements at all. Remove that
  gate everywhere (coverage_gate, readiness panel, stepper, approvals).

## 2. Any SOW can be deleted at any stage, including approved or signed

- Delete is available from the SOW row menu and the SOW page. The
  confirm dialog lists what goes with it (versions, GM, staffing,
  approval package, tasks, files).
- Delete really removes it from every list, queue, board and dashboard,
  so a fresh SOW can be submitted in its place.
- Keep one line in the audit log for each deletion: who, when, SOW name,
  stage it was in, price. Nothing else is kept. That line is the only
  record that it existed.
- Deleting a client deletes its SOWs the same way. Remove the "approval
  trail is append-only, archive only" refusal.

## 3. Clean staging for my testing

- Hard-delete all test data: every client, SOW, agreement and task
  created by e2e runs, smoke fixtures or earlier slices (S12 to S16,
  "S14b e2e ...", "smoke fixture", Peppermill copies).
- Leave the users, groups and settings. Keep the one fixture the deploy
  smoke script needs, and make the smoke script create and delete its
  own data so it never shows up in my lists again.
- Report the counts deleted.

## 4. Proof with screenshots

Upload an NDA and an MSA for a client; upload a SOW with the checkbox
ticked; submit and approve it; delete it from the approved state;
submit a fresh one for the same client with no duplicate warning. Show
the empty lists after cleanup and the audit-log deletion line. Then
send me the staging URL and a 4-step click-through.

## Addendum

Same branch, same proof.

1. Delete is one operation, visible everywhere. Deleting a SOW (or a
   client) removes it at once from every place it appears: SOW approvals
   board, Pipeline clients, Command center, Projects, Renewals, Signed
   handoff, My work tasks, search, notifications and reports.
   - Implement it as ONE server-side delete service that every screen's
     data comes through. Do not patch each page separately.
   - Clear the related tasks, pending approvals and queued notifications
     in the same transaction.
   - Add a test that creates a SOW that appears on all those screens,
     deletes it, and asserts every list endpoint no longer returns it.
2. The /sows board is full of E2E Staging Bot packages I never created.
   Delete all of them in the staging cleanup, with the count in the
   report. Then fix the cause:
   - Every e2e and smoke run creates its data under a run tag and
     deletes it in teardown, including when the run fails.
   - Add a nightly job on staging that deletes any e2e-tagged data older
     than 24h, so nothing leaks into my lists again.
3. Board cards:
   - Show the SOW title and client name, never an ID or hash.
   - Show approver names, never "Name unavailable". If a user can't be
     resolved, show "Unassigned".
   - Drop the NDA/MSA chips per S17.

Proof adds:

- A screenshot of `/sows` empty after cleanup.
- The delete-everywhere test passing.
- A screenshot of one real SOW deleted from the board and then missing
  from Pipeline and Command center.
