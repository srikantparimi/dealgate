# S1 E1 — Audit log viewer

## User story
As Finance, Legal or the CEO, I open the audit log for a deal or a client and
see every state change with actor, timestamp, before/after and correlation id,
so that I can answer "who approved what, when, on what package".

## Acceptance tests (Given/When/Then)
- Given a deal has moved through Intake → Coverage → SOWDraft, when I open
  the deal's audit tab, then I see three rows newest first with actor + timestamp.
- Given an `audit_event` row exists, when I attempt to update or delete it via
  the API or DB, then the operation is refused (append-only + hash chain).
- Given I am not in Finance, Legal, CEO or SystemAdmin, when I request the
  audit endpoint, then I get 403.

## Data touched
- Tables: `audit_event(id, ts, actor_id, action, entity, entity_id, before jsonb,
  after jsonb, correlation_id, prev_hash, row_hash)`.
- Immutable versions written: every row (append-only).
- Audit events emitted: n/a (this is the sink).

## Roles allowed
- `Finance`, `Legal`, `CEO`, `SystemAdmin`: read.
- Nobody: write via API. Rows are written from inside workflow transitions only.

## Out of scope
- Nightly export to S3 with Object Lock (Sprint 5 / hardening).

## Notes
- Blueprint §12 (audit chain, append-only, no UPDATE/DELETE by the app user).
- The application DB user has no UPDATE or DELETE grant on `audit_event`.
