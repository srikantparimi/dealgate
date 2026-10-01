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

14. **Branch discipline.** All work happens on a feature branch. The branch
    deploys to staging, `scripts/deploy-smoke.sh` is green, the slice's own
    proof passes, and for user-facing slices the product owner has clicked
    through it. Only then does it squash-merge to main. Main is always
    releasable. Adopted with S16.

15. **Interactive terraform prompts are stop points, not automation
    surfaces.** Never pipe `yes`, `echo yes`, `printf` or any other
    scripted answer into `terraform init` (`-reconfigure` /
    `-migrate-state`), `terraform apply` (state-lock overrides, resource
    replacements, destroy plans) or any other interactive terraform
    prompt. If a prompt appears, stop and show it to the operator
    verbatim. The prompts exist because the answer changes state that
    cannot be undone from a shell one-liner. Additionally, `terraform
    init` refuses to run when any `terraform.tfstate*` file (other than
    `*.stale.bak`) sits in `infra-tf/`: `scripts/tf-init.sh` is the
    only supported entry point and it fails the run with a pointer to
    the S14a.1 ADR when a stale local state is detected. Adopted
    29 Sep 2026 after a scripted `yes` to `terraform init -reconfigure`
    briefly overwrote the S3 state with a Sept-17 laptop file (root
    cause: local state files never deleted per the S14a.1 post-
    migration step, so a returning `init` had material to overwrite
    with). See `docs/reports/s19-1-progress.md` §"Incident during I1"
    for the recovery.

16. **Session budget and item-by-item reporting.** Every session states
    its budget at start (default: 60 min wall clock, 5,000 tokens of
    output) and stops when it hits it, writing the progress file and
    a report. Reports list every numbered item of the directive, by
    number, in exactly one of the five states
    (`verified working (staging)` / `fixed and tested` / `missing` /
    `blocked` / `deferred`) with its proof; an item not listed is a
    report defect. "Complete", "all shipped" or "zero deferrals" may
    appear only when every item is `verified working (staging)`.
    Investigation without a stated hypothesis is stopped after 10
    minutes. Adopted 30 Sep 2026 after S20 Session 3b's initial report
    glossed items 1–3 of the directive with "already deployed" instead
    of stating each in the five-state vocabulary — the fix required a
    Rev-2 pass to land chip value, owner + BU selects, and the T35
    pytest, and to re-report the three lines explicitly.

    **Scoreboard discipline (1 Oct 2026):** every session's first and
    last tool actions on `docs/reports/s20/scoreboard.md` are to
    update the rows it owns. First action: mark rows the session will
    attempt; last action: flip states to the final value with proof +
    session id filled. ETA at the bottom of the scoreboard =
    (rows not `verified working (staging)`) ÷ 7 per session.

17. **Parallel lanes.** When S20 splits into feature lanes
    (`feat/s20-<lane>`), each lane works on its own branch — only the
    Lead deploys to staging. A lane proves its work locally: pytest
    against the CI Postgres fixture, Playwright against a local dev
    server. **Lanes never run tests against staging and never deploy
    themselves.** A lane edits only its owned files + its own
    scoreboard rows; anything else, ask the Lead in
    `docs/reports/s20/progress-<lane>.md` and don't touch.

    - **Lane A** (`feat/s20-w4`): no migrations. Owned files —
      `api/app/routers/{reports,dashboards,settings}*`,
      `api/app/services/hubspot_pipeline.py` **(summary only — nothing
      else in that file)**,
      `web/src/pages/{Reports,CommandCenter,Settings,SystemHealth}*`.
    - **Lane B** (`feat/s20-w7`): owns alembic revisions **0048+**.
      Owned files — `api/app/routers/{sows,approvals,signature,projects}*`,
      `api/app/services/{signature,release,projects,forecast}*`,
      `api/app/services/signed_sow.py`,
      `web/src/pages/{SowWorkspace,Projects,Handoff}*`, migrations.

    - **Shared, append-only** (D-S20-17a, 1 Oct 2026): any lane may
      **add** to the following files; no lane edits or removes
      existing lines; the Lead merges additions on rebase. Paths —
      `web/src/api/client.ts`, `web/src/routes*.tsx`,
      `web/src/nav*.tsx`, and the router-registration block in
      `api/app/main.py`. On merge conflict in these files the
      resolution is to **keep both lanes' additions** (concatenate,
      do not drop). Anything beyond pure additions in a shared file
      remains a rule-17 violation and a stop condition.

    Lanes merge back to `integrate/s20` only through a Lead rebase +
    checkpoint; alembic head must stay == 1 after merge or the Lead
    stops and reports. Adopted 1 Oct 2026 to let W4 (reports +
    integrations + health) and W7 (approval → delivery) progress in
    parallel without stepping on each other's files or staging.

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
