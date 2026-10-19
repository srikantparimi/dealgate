# S2 E3 — Agreements (NDA/MSA) CRUD + evidence upload + expiry

> **Superseded.** This story's agreement lifecycle (the ten-state machine, owner, due date, effective and expiry dates) was removed in S17. Since S24-AG1 an NDA or MSA has one of seven states (Client copy, Standard copy, Marked covered, Missing, Due at stage 2, Not needed now, Existing, none attached) from the shared service `api/app/services/agreement_status.py`, and a missing document only warns: nothing blocks review or signature. See `docs/directives/s24-ag1-agreements.md` and `docs/reference/openapi-agreements.yaml`. Kept as the historical record of what was asked.

## User story
As Legal, I create and maintain NDA and MSA records on the client legal
entity. Each has a state, owner, next action, due date, effective / expiry
dates, notice rule, and an uploaded evidence file. The system alerts me
60 days before expiry (agent N — alert scheduler owns the scheduling).

## Acceptance tests (Given/When/Then)
- Given a `legal_entity` exists, when Legal POSTs `/agreements` with type=NDA,
  state=drafting, owner_email, due_date, then a row is created and audited
  `agreement.created`.
- Given an agreement is in `sent for signature`, when Legal PATCHes to
  `executed` with an uploaded evidence file (S3 pre-signed PUT then confirm),
  then state transitions, evidence key persists, `expiry` is required.
- Given an agreement transitions to a state not in the state machine
  (e.g. missing → executed), then 422 with a clear error and no audit row.
- Given a non-Legal role attempts POST/PATCH → 403.
- Given a role with cost visibility (Finance) tries to read `/agreements`,
  then no cost fields are surfaced (agreements don't carry cost).
- Given the agreement is `executed` with expiry in 60 days, when the alert
  scheduler runs (mocked with time-travel in tests), then a task is created
  for the Legal owner (integration test in Agent N's story).

## Data touched
- `agreement` table: enum column `state` (missing/requested/drafting/under_review/sent/partially_signed/executed/expired/terminated/superseded).
- `agreement_state_transition` allowed list encoded in code.
- Evidence uploads: S3 bucket `officeapp-dev-agreements-{account_id}` with SSE-KMS + versioning + Object Lock later.

## Roles allowed
- Legal: create, patch state, upload evidence.
- SystemAdmin: same.
- All governance roles: read.

## Out of scope
- Automatic OCR of the evidence file.
- Signature via e-sign provider (manual upload for pilot).

## Notes
- Blueprint §6.2 for the state list.
- Alert scheduler in Agent N reads `expiry` for the 60-day warning.
