# S2 E3 — My tasks inbox + task lifecycle

## User story
As any role, I open "My tasks" and see everything assigned to me, ordered by
due date. I can accept, complete, snooze, or reassign a task; every action
is audited. Escalation levels bump when SLAs pass (alert scheduler owns the
timer; this story owns the UI + endpoints).

## Acceptance tests (Given/When/Then)
- Given I have 5 tasks assigned, when I GET `/tasks?owner=me`, then all 5
  return sorted by due_date ASC NULLS LAST.
- Given a task in status `assigned`, when I PATCH to `in_progress`, then
  status transitions and audit event `task.started` fires.
- Given I attempt an invalid transition (e.g. `done` → `assigned`), then 422.
- Given a task is `overdue` (escalation_level > 0) and I complete it, then
  audit records the completion with `escalation_at_completion`.
- Given I try to complete someone else's task without being a leader, then 403.
- Given the task is `snoozed` with a `wake_at` date, then it disappears
  from "My tasks" until wake_at is reached.

## Data touched
- Extend `task` model: add `status`, `wake_at`, existing escalation_level used.
- Transitions: assigned → in_progress → done; assigned → snoozed → assigned; assigned → reassigned; * → cancelled.

## Roles allowed
- All authenticated users: read own tasks.
- Sales leader / HR leader / SystemAdmin: reassign any task.

## Out of scope
- Bulk-complete (add later).
- Comments on tasks.

## Notes
- The alert scheduler (Agent N) is the writer of tasks; this story is
  reader + lifecycle only.
