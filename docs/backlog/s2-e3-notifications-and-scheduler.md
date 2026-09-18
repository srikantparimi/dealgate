# S2 E3 — Notification engine + alert scheduler

## User story
As any role, notifications reach me via email (and Teams/Slack if configured)
when a task is assigned, when a check-in date passes, when an approval is
waiting past SLA, or when an agreement is close to expiry. The system uses
a transactional outbox so a committed decision always produces its
notification even if the send fails.

## Acceptance tests (Given/When/Then)
- Given a state transition writes an audit event AND a `notification` row
  in the same transaction, when the delivery worker picks up the outbox,
  then it sends via SES; on 5xx it retries with exponential backoff up to
  5 attempts.
- Given a user's `NotificationSetting.email=off`, when a notification is
  queued for them, then it is marked `suppressed` with reason.
- Given an agreement `expiry` is in exactly 60 days (time-travel via env
  `DEALGATE_NOW`), when the scheduler tick runs, then a task is created for
  the Legal owner AND a `notification` outbox row is queued.
- Given a task passes its `due_date`, when the scheduler tick runs, then
  `escalation_level` increments and a notification is queued to the owner's
  function head.
- Given SES is unavailable (mocked failure), when the delivery worker runs,
  then rows stay pending with `attempts>0` and `next_attempt_at`.
- Given a user opens Notification Settings, then they can toggle per-channel
  (email, teams/slack, in-app) for categories (task_assigned, approval_pending,
  expiry_warning, escalation).

## Data touched
- New tables: `notification` (outbox), `notification_setting` (per user × category × channel).
- Extend `task` model with escalation timestamp fields.

## Roles allowed
- Read own settings: all roles.
- Send notifications on someone else's behalf: nobody via API. The worker is
  the only writer.

## Out of scope
- Digest / batching (send-per-event for Sprint 2).
- Push notifications, SMS.

## Notes
- Blueprint §9 (triggers table).
- SES is in sandbox by default; only verified addresses receive real email.
  In dev we verify `srikantp@smartek21.com` and use it as both sender and
  test recipient. Real production access-out-of-sandbox is a separate ticket.
