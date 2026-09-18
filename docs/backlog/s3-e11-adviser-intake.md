# S3 E11 — Opportunity Adviser: intake form + pricing service

## User story
As Marketing, I fill in a short intake describing what the client wants,
and get back an indicative team, effort, cost range, and minimum price
per delivery option (US-only, India-only, Mixed). Every estimate is
labeled "Indicative estimate, requires Delivery and Finance validation".
The estimate is never a quote.

## Acceptance tests (Given/When/Then)
- Given I POST `/adviser/estimates` with `client_name`, `problem`, and the
  optional fields, when the pricing service runs, then response includes
  scope interpretation, proposed team, cost range, min price for US/India/Mixed.
- Given the model returns fewer than 3 roles or asks clarifying questions,
  then the response is a `questions` array instead of an estimate.
- Given I am not Marketing/Sales/Presales/SystemAdmin, then 403.
- Given the estimate is generated, then the response's `label` field is
  exactly `"Indicative estimate, requires Delivery and Finance validation"`
  (verified in tests).
- Given the pricing service is asked to produce a PDF, then 404 (no PDF
  export per the risk mitigation in §15).
- Given the adviser output is logged with model + prompt_version + sources,
  then a `adviser_estimate` row exists with those fields.

## Data touched
- New table: `adviser_estimate` (inputs, structured output, sources, model, prompt_version, reviewer_id nullable).

## Roles allowed
- Marketing, Sales, Presales, SystemAdmin: submit.
- All governance roles: read.

## Out of scope
- Public web search (part of the fuller adviser in Sprint 4).
- Auto-drafting a SOW (never — always human).

## Notes
- Blueprint §5 (guardrails).
- Deterministic pricing = math in `api/app/gm` × rate_cards. LLM only
  proposes roles/hours as structured JSON.
- Bedrock model + prompt version stored per row so future retuning is
  auditable.
