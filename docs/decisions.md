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
