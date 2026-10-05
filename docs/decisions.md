# DealGate · Decisions log

One entry per decision that changes a standing rule or scope. Each
entry carries an id, date, decision, context, and scope. Decisions
are append-only; superseded entries get a "Superseded by Dxxx" note
but stay in place.

## D-S20-17a · Shared, append-only file class for parallel lanes

- **Date:** 2026-10-01
- **Decision:** Rule 17 (parallel lanes) adds a "shared, append-only"
  file class covering `web/src/api/client.ts`, `web/src/routes*.tsx`,
  `web/src/nav*.tsx`, and the router-registration block in
  `api/app/main.py`. Any lane may **add** functions, routes, or
  registrations in these files; no lane edits or removes existing
  lines; the Lead merges the additions. Separately,
  `api/app/services/signed_sow.py` is added to Lane B's owned list.
- **Context:** C1 (2026-09-30) found Lane A edited `client.ts`
  (shared) and Lane B edited `client.ts` + `signed_sow.py` (not in
  the Lane B owned glob). Both edits were additive and necessary —
  new API client helpers for Reports/CC cards/integration cards
  (Lane A) and signatory-diff helpers in signed_sow (Lane B). A
  one-off exception without a rule change would recur every
  checkpoint; the pattern is the rule.
- **Scope:** effective for S20 and future parallel-lane work.

## D-S20-17b · Additivity in shared-append-only files is a tsc check, not a line-count check

- **Date:** 2026-10-01
- **Decision:** Additive, for the purposes of rule 17's shared,
  append-only file class, means: widening a type (e.g. broadening a
  union), adding a union member, adding an enum member, or adding
  an optional field. Narrowing a type or removing a member/field is
  NOT additive. The Lead verifies additivity on the merged tree by
  running `tsc --noEmit`; diff line counts (added vs removed) are
  no longer the gate.
- **Context:** C1-resume (2026-10-01) stopped Lane B because the
  diff on `web/src/api/client.ts` had 4 removed / 13 added lines —
  Lane B had added `signatories` to the `SignedSowFieldName` union
  and widened `SignedSowDiffField.approved`/`.extracted` from
  `string | null` to `string | string[] | null`. Both edits are
  type-wideners: no existing caller is broken (the superset
  accepts every value the subset did). A line-count rule rejects
  non-breaking widenings and forces lanes to invent parallel
  sibling types for every schema evolution — pure friction, no
  safety gain. The tsc gate catches the actual breakage (narrowing
  / removal) directly.
- **Scope:** effective for S20 and future parallel-lane work.
  Supersedes the "no edits/removes to existing lines" clause of
  D-S20-17a for shared-append-only files.

## D-S21F-02: Three-Hour Autonomous Execution Windows

- Date: 2026-10-02 UTC; explicitly authorized by the product owner in chat.
- Scope: S21 and Forecast v3 on feat/s21-forecast only. Supersedes the
  repository 60-minute limit and its minute-55 deployment trigger for this
  work; all other rules and human approval/release controls are preserved.
- First resumed window: 2026-10-02 01:26:53 through 04:26:53 UTC. Resume
  inspection confirmed clean HEAD eb0434788d83ab325a552f72671d64b8609ff7f7;
  no subsequent work was overwritten.
- Checkpoint approximately every 30 minutes and before risky operations.
  Checkpoints, tests, fixes and lane integration need no acknowledgment.
  At three hours write a complete handoff and continue another window when
  the runtime supports it. Explicitly disclose any forced stop and its
  exact resume command; no fictional background continuation.
- Preserve one-worker capacity until measured headroom justifies two;
  workers retain separate branches, worktrees, runtime and file ownership.
  Lead alone integrates, orders migrations and deploys.
- Interrupt only for an approval-ready exact infrastructure plan, exhausted
  access/material business blockers, or fully tested staging click-through
  and merge approval. Continue independent work around dependencies.
- No weakened assertions, scope reduction, premature completion claim,
  automatic Terraform approval or main merge without explicit acceptance.

## D-S21F-03: Versioned Mandatory Sales Review

- Date: 2026-10-02 UTC. Implements v3 S21-05/06; HR remains mandatory.
- New submissions use routing policy 2: Delivery, HR and Sales must all
  finish before the existing Finance/Legal stage, then conditional CEO.
  Sales joins the first functional stage; existing Finance/Legal and CEO
  ordering is preserved. The historical status identifier remains stable.
- Store the policy version on each immutable package. Migration marks
  existing cycles policy 1 without fabricating a Sales decision or changing
  a historical signed approval basis. Resubmission uses policy 2.
- Preview keeps missing-reviewer reasons visible; submission rejects any
  missing mandatory reviewer, including a required CEO. No-plan service
  calls must resolve and freeze the same assignments as HTTP submission.
- UI receives required_functions from the frozen package; old packages
  retain four review marks, new packages five. No inferred retroactive pass.

## D-S21F-04: Permanent SOW Deletion With Retained Financial Dependencies

- Date: 2026-10-02 UTC. Explicit v3 S21-01/CO-09 replaces S20 Archive-only
  refusal at every SOW stage; existing role and trusted-fixture controls remain.
- Preserve parent deal/client, sibling SOWs, client agreements and independent
  opportunities. Current opportunity-wide package deletion is not a valid
  ownership boundary and must be narrowed before enabling governed deletion.
- Retain projects and financial actuals with detached, labeled source links.
  Only positively proven empty generated project shells may be removed; retain
  all projects initially rather than infer emptiness from missing integration data.
- Commit database removal, audit, minimal deletion fence and retryable storage
  cleanup job together. Object failure is pending/failed cleanup, never success.
  Do not retain deleted upload/extraction payload in the tombstone. Historical
  append-only audit and retained financial facts remain protected.
- Migration0052 reserved by lead, not yet implemented/applied. Tests and real
  dependency/storage/fault proof precede activation. See docs/s21/contracts.md.
