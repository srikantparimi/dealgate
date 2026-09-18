# S4 E2 — HubSpot write-back (three governance properties)

## User story
When a deal's governance status or approved GM % changes, the system writes
back exactly three HubSpot custom deal properties (read-only from HubSpot's
perspective, editable only by DealGate): `dealgate_governance_status`,
`dealgate_approved_gm_pct`, `dealgate_link`.

## Acceptance tests
- Given a package moves to `ready_to_sign`, when the write-back job runs,
  then HubSpot deal properties reflect the new governance status and
  approved GM %. Idempotent: rerunning the job with the same state is a
  no-op.
- Given the HubSpot API returns 429, then the job retries with backoff and
  eventually succeeds; failures after MAX_ATTEMPTS record `hubspot_write.failed`.
- Given the deal is deleted in HubSpot (404), then the job records
  `hubspot_write.deal_missing` and does not create the deal.
- Given a webhook comes back after a write-back, then the deal state is
  NOT changed by the payload (the write-back stays as source of truth for
  those three fields).

## Data touched
- New table: `hubspot_writeback_job` (id, deal_id, target_state JSONB,
  status, attempts, last_error).

## Roles
- No user endpoint. The worker processes queued jobs and audits every
  attempt.

## Out of scope
- Two-way sync (out of scope forever — HubSpot is master for the
  non-governance fields).

## Notes
- Blueprint §6.1 + §12 (three properties only).
