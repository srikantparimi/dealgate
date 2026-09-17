# worker/ — SQS consumers, schedulers, AI jobs

Sprint 0 leaves this as a placeholder. Handlers land per epic:

- `hubspot_intake` (S1) — consume HubSpot webhook events, re-read the deal,
  upsert `opportunity`, create the intake task. Idempotent on
  `integration_event.source_event_id`.
- `nightly_reconcile` (S1) — walk HubSpot deal ids modified in the last 24h,
  catch anything the webhook missed.
- `alert_scheduler` (S2) — daily job that opens tasks and sends outbox
  notifications (see docs/build-guide.md §9).
- `sow_extract` (S3) — Bedrock + Textract job that returns SOW fields with
  page refs as JSON validated by schema.
- `ceo_brief` (S4) — Bedrock job that drafts the exception brief from the
  package.
- `signed_diff` (S5) — re-extract the executed SOW and diff it against the
  approved package; hold release on mismatch.

All jobs use the same `Job` interface: input JSON schema, deterministic output
JSON schema, and no side effects outside the database transaction and the
outbox.
