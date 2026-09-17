# S1 E2 — HubSpot webhook intake

## User story
As Sales, when a deal is created in HubSpot, it appears in DealGate within two
minutes with an intake task assigned to the deal owner, so that no deal goes
unowned.

## Acceptance tests (Given/When/Then)
- Given HubSpot sends a valid `deal.creation` webhook, when the webhook Lambda
  receives it, then the payload is placed on SQS and 200 is returned within 5s.
- Given the worker consumes the event, when it calls the HubSpot API for the
  deal, then it upserts `opportunity` by `hubspot_deal_id` and creates an
  `intake` task assigned to the mapped user.
- Given the same event id arrives twice, when the worker consumes both, then
  only one `opportunity` and one `task` exist (idempotent).
- Given the webhook signature is invalid, when the Lambda receives it, then
  the request is rejected with 401 and nothing is enqueued.
- Given a deal has no owner in HubSpot, when the event is processed, then the
  intake task is assigned to the Sales leader (config), not left unassigned.

## Data touched
- Tables: `opportunity`, `task`, `integration_event(source_event_id UNIQUE)`.
- Immutable versions written: `integration_event` rows (for dedupe + replay).
- Audit events emitted: `opportunity.created`, `task.created`.

## Roles allowed
- The HubSpot Lambda is unauthenticated at the ALB but requires a valid v3 signature.
- Manual replay of an event: `SystemAdmin` only.

## Out of scope
- Nightly reconciliation job (separate story in S1).
- Writing back the three governance properties to HubSpot (S4).

## Notes
- Blueprint §6.1 — never trust the webhook payload; re-read from HubSpot.
- Blueprint §7 (agents) — Sales leader routing is a config value, not a hardcoded id.
