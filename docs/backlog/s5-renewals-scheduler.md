# S5 E9 — Renewals scheduler + notice-date rules + escalation

## User story
When a SOW is 2 months from its term end, the system opens a `renewal`
record and files a task with the account owner to record status/value/
decision/next action. Every 7 days the system asks for a substantive
update. Contractual notice dates earlier than 2 months get their own
Legal task. 30 and 14 days from expiry unresolved escalate to leadership.
Expired SOWs with no extension are flagged; new commitments blocked.

## Acceptance tests
- Given a SOW `term_end = today + 60 days`, when the renewal scheduler
  runs, then a `renewal` record is opened + task created for account
  owner. Second tick same window: idempotent (no dupe).
- Given `notice_date < term_end - 60 days`, then a Legal-owned task is
  filed at notice_date - 60 days (independent alerts).
- Given `term_end = today + 30`, when the scheduler runs, then leadership
  escalation notification queued (category `escalation`).
- Given `term_end = today + 14`, same → second escalation.
- Given `term_end < today` and no extension, then renewal status transitions
  to `churn`; new commitments on that SOW blocked (approval submit → 409).
- Given a short assessment SOW (term ≤ 4 weeks) signed within 60 days of
  end, renewal review opens immediately.

## Data
- `renewal` table (see s5-signed-sow-distribution.md).

## Roles
- Scheduler is a worker; system-owned writes.
- Read: any governance role.

## Notes
- Blueprint §9 (renewal rows in the triggers table).
- Uses Agent M's queue_notification + Agent N's scheduler pattern.
