# S2 E4 — Rate cards + policy admin (Finance-only)

## User story
As Finance, I own the planning cost bands by role/seniority/location and the
US/India margin floors and FX convention. I edit these in the app; every
edit produces a new immutable version tied to an effective date, and every
GM calculation records which policy_version + rate_card_version it used.

## Acceptance tests (Given/When/Then)
- Given I am Finance, when I POST `/admin/rate-cards` with a new set of rows,
  then a new immutable `rate_card_version` is created with `effective_from`,
  audit event `rate_card.published`.
- Given a rate card exists, when Finance PATCHes it, then the response is
  409 (immutable) — Finance must publish a new version instead.
- Given I am not Finance/SystemAdmin, when I GET `/admin/rate-cards`, then 403.
- Given a rate card row has a cost < some sanity floor (e.g. $5/hr), then
  the create validates but flags a warning in the response — Finance can
  override with `confirm=true`.
- Given a policy row exists with US floor 0.35 and India floor 0.50, when
  Finance publishes a new policy with US floor 0.40, then subsequent GM
  calculations use the new floor; existing packages keep their frozen
  policy_version.
- Given Finance publishes a policy with US floor > India floor, then 422.

## Data touched
- New tables: `rate_card`, `rate_card_row`, `policy`, `policy_version`.
- Money `NUMERIC(14,2)`, rates `NUMERIC(10,4)`.
- All rows tagged with `effective_from` (date) and immutable after publish.

## Roles allowed
- Finance + SystemAdmin: read + create.
- Delivery + HR: read (they need to see planning bands).
- Sales/Marketing: 403 on rate cards; they never see cost bands.

## Out of scope
- FX rate feeds (manual for Sprint 2; scheduled fetch in a later sprint).

## Notes
- Blueprint §7 (Finance owns rate cards, FX, and what counts as delivery cost).
- Sample seed data lands in `fixtures/rate_cards/dev.json` (Agent P also uses this for the Excel template spec).
