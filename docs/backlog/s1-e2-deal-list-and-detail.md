# S1 E2 — Deal list and Deal detail

## User story
As Sales, I open DealGate and see my deals with governance status, next client
action and any missing coverage (NDA/MSA); as an exec, I see all deals filtered
by owner, stage or blocker, so that I never have to ask "where does this stand".

## Acceptance tests (Given/When/Then)
- Given I am Sales with deals assigned, when I open the Deal list, then it
  defaults to `owner = me` sorted by next client action date ascending, and
  each row shows: client, engagement type, sales stage, governance status,
  next action, coverage state.
- Given I open a Deal detail, then the page shows intake panel (owner,
  engagement type, next client date), coverage panel (NDA/MSA states),
  activity/audit tab, and any assigned tasks — no SOW or GM panels yet
  (those ship in S3).
- Given I am not the owner and not a leader role, when I try to change the
  owner or next action, then the endpoints return 403.
- Given a deal has no engagement type set, when a governance status check
  runs, then it remains in `Intake` and the intake task is not auto-completed.

## Data touched
- Tables: `opportunity`, `task`.
- Immutable versions written: none.
- Audit events emitted: `opportunity.owner_changed`, `opportunity.next_action_updated`.

## Roles allowed
- All roles can read deals they can see per row-level policy (owner + leader roles).
- Only the owner or `Sales` leader may change owner / next action.

## Out of scope
- SOW upload, GM sheet, approvals (S3 / S4).
- Bulk actions.

## Notes
- Build-guide §13 sprint plan: S1 delivers Login, Deal list, Deal detail,
  Users/roles admin, Audit log viewer.
- Pages assemble from `web/src/ui` primitives only.
