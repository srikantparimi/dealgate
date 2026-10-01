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
