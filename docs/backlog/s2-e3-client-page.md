# S2 E3 — Client page with agreements (unblocks coverage_state)

## User story
As Sales/Legal/Finance/CEO, I open a client page and see the client's legal
entities, all NDA/MSA agreements with state + expiry, all opportunities, and
recent audit activity. The Deal list's `coverage_state` column now reflects
real NDA/MSA status per client, not "No client linked".

## Acceptance tests (Given/When/Then)
- Given a `client` row exists with two agreements (executed NDA, missing MSA),
  when I GET `/clients/{id}`, then the response includes `legal_entities[]`,
  `agreements[]`, `opportunities[]`, `coverage_state` = "MSA missing".
- Given a HubSpot webhook creates a deal, when the intake worker upserts the
  opportunity, then it also upserts a `client` (by `hubspot_company_id`) and
  a default `legal_entity`, and sets `opportunity.client_id`.
- Given I am Sales and the client is mine, when I GET `/clients/{id}`, then
  200; not mine and not a leader → 403.
- Given a client has three opportunities, when the Client page renders, then
  the coverage summary badge shows the worst state across its agreements.
- The DealList row `coverage_state` now uses the client's real agreements
  (not the placeholder "No client linked").

## Data touched
- New migration: `opportunity.client_id` FK (nullable at first for backfill; NOT NULL after).
- `client.hubspot_company_id` unique constraint.
- Read-only: `legal_entity`, `agreement` (Sprint 1 skeleton fleshed out by Agent K in parallel).

## Roles allowed
- Read: Sales (own), Presales, Delivery (own), Finance, Legal, CEO, SystemAdmin.
- Mutate `client.*`: SystemAdmin only for Sprint 2; Sales-leader can be added later.

## Out of scope
- Agreement CRUD (Agent K owns that story in parallel).
- Deleting clients.

## Notes
- Blueprint §6.2 (coverage tied to legal entity, not the deal).
- Fixes the Sprint 1 question in `docs/questions.md` about opportunity→client linkage.
