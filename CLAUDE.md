# DealGate — Standing rules for every agent

These rules are policy for every PR. If a rule and a ticket conflict, the rule wins.

1. `docs/blueprint.md` is policy. `docs/build-guide.md` is design. If they conflict
   or are silent, stop and write a question in `docs/questions.md`. Do not guess
   on margin policy, approval order, or who can see cost.
2. All money uses Python `Decimal` and `NUMERIC` columns. No floats. All margin math
   lives in `api/app/gm` and nowhere else. LLMs never compute or alter a number.
3. Write the acceptance test from the story file before the implementation.
4. SOW, GM and approval records are immutable versions. Never `UPDATE` them.
5. Every state transition goes through `api/app/workflow`, checks role server-side,
   and writes an `audit_event` in the same transaction.
6. AI output is a draft with sources and page refs, validated against a JSON
   schema, and needs human confirmation before it affects a record.
7. HubSpot is master for deal identity, owner, stage. Write back only the three
   governance properties. Handlers are idempotent; dedupe on event ID.
8. No secrets in code. No real client data in fixtures. One story per PR,
   under ~400 changed lines, green pipeline before review.
9. Every story is a vertical slice: migration + API + page + tests in one PR.
   No backend-only or UI-only feature PRs, no pages on mock data. Build pages
   from the shared UI kit in `web/src/ui`; no business math in the browser.
   A story is not done until a human can complete it in the browser on staging.
10. **Every field has a provenance** (`extracted` / `looked_up` / `calculated` /
    `defaulted` / `manual`). `manual` requires a written justification in the
    story file for why the value cannot be derived from the SOW, master data,
    or a calculation. **A blank form on open is a defect.** Pre-filled is
    the default state; screens confirm what the system decided, they do not
    ask a person to type it. See `docs/directives/sow-first.md`.
11. **No "not wired" throwers.** If a control is visible on any screen it
    works end-to-end against the deployed backend, or the control is deleted.
    CI greps for `not wired`, `TODO: stub`, `Not implemented`, `Follow-up
    story` and equivalents and fails the build. Words like "sizable but the
    right shape", "the right approach is", "pilot" and "prototype" in code
    or PR text are the same defect in a different form. Build the path or
    delete the button.
12. **No infrastructure changes via console or CLI, ever.** Every AWS,
    CloudFront, ECS, RDS, IAM, Cognito or Secrets Manager change goes
    through Terraform in a PR. This includes ECS task-def re-registrations,
    CloudFront distribution edits, S3 bucket policies, and Cognito user
    pool client rotations. If Terraform can't express it yet, the story
    is to teach it — not to bypass it. Adopted 22 Sep 2026 after S14a
    exposed 61 drifted resources from months of hand-applies never
    round-tripped into state.
13. **Every blocker is an editor.** If a "What's still needed" row (or
    any other place that names a missing field) is visible on a page,
    that page must render an inline input for the field — no naked
    "Jump to field" that points at another screen. Blockers that
    legitimately live in another section carry a redirect editor
    component that names where to go; the row still gets an editor
    entry. A blocker key with no editor is itself a bug — the
    `blockerRegistry` completeness test fails the build if a canonical
    key lands without an entry. Adopted 23 Sep 2026 after S15 found
    that the signatories-picker fix was a one-off; the pattern was the
    requirement.

## Where things live

- `docs/blueprint.md` — the governance policy (source of truth for rules).
- `docs/build-guide.md` — this build's design; do not restate it in code comments.
- `docs/adr/` — one short file per architecture decision.
- `docs/backlog/` — one markdown file per story, with acceptance tests (Given/When/Then).
- `docs/questions.md` — open questions blocking work; the lead answers these.
- `api/app/gm/` — pure calculation library, no I/O, 100% covered.
- `api/app/workflow/` — state machine, role checks, audit emission.
- `api/app/integrations/` — HubSpot, SES, Teams/Slack, Bedrock.
- `web/src/ui/` — shared components (app shell, table, form, status chip, approval card).

## Definition of done (every story)

- Acceptance tests written first and passing.
- Permission test for each new endpoint.
- `audit_event` emitted on every state change.
- Migration is reversible.
- Deployed to staging by the pipeline.
- A human from the owning function has clicked through it.
