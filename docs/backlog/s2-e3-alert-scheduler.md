# S2 E3 — Alert scheduler + notification sender (worker)

## User story
As the system, every scheduler tick I create tasks and queue notifications
for: new deals without an owner, client check-ins with no update in 3 days,
NDA/MSA agreements expiring within 60 days, expired agreements, and
approvals waiting past their SLA. Every notification queued in the outbox
gets sent by the sender worker via SES; failures retry with backoff.

## Acceptance tests (Given/When/Then)
- Given an agreement executed with `expiry = today + 60`, when the scheduler
  runs (time-travel via `DEALGATE_NOW`), then exactly one task is created
  for the Legal owner AND one notification queued per their enabled channels.
- Given the scheduler runs twice for the same trigger, then only one task
  and one notification are created (idempotency key on the trigger).
- Given `expiry = today + 90`, then no task is created (outside window).
- Given `expiry = today - 1`, then a `agreement.expired` task is created.
- Given an opportunity `next_client_date = today - 4 business days` with no
  intervening `opportunity.next_action_updated` audit, then a task is
  created for the account owner AND escalated to the Sales leader if
  configured.
- Given the notification sender picks up a `pending` notification, when
  SES returns 200, then the row moves to `sent` with `sent_at` timestamp.
- Given SES returns 500 (mocked), then the row's `attempts` increments and
  `next_attempt_at` uses exponential backoff up to 5 attempts, then `failed`.
- Given the user's `notification_setting.channel=email` is off, then no
  email row is inserted for that user × category (Agent M enforces at queue
  time; the scheduler tests confirm this end-to-end).

## Data touched
- Reads: `opportunity`, `agreement`, `task`, `notification`.
- Writes: `task` (new), `notification` (new), `audit_event`.

## Roles allowed
- The scheduler runs as a system role. All writes carry `actor_id = null` +
  `action = 'scheduler.<trigger>'` in the audit chain.
- No user-facing endpoint (scheduler is a worker).

## Out of scope
- Renewals scheduler (that's Sprint 5).
- Teams/Slack senders (Sprint 2 delivers SES only; Teams/Slack lands with
  a config toggle later — the notification rows for those channels stay
  `suppressed` for now with a clear reason).

## Notes
- Blueprint §9 (triggers table — this story implements rows 3 and 4 of
  that table; renewals are §9 rows 5-7 in Sprint 5).
- SES sandbox: only verified addresses receive real mail. In dev,
  `srikantp@smartek21.com` is verified; the test recipient is the same.
