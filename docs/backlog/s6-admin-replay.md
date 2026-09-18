# S6 admin — Replay screen for failed integration events + DLQ

## User story
As SystemAdmin, I open the admin replay screen and see failed
`integration_event` rows and failed `notification`/`hubspot_writeback_job`
rows. For each I can view the payload, view the last error, and trigger a
replay (which re-runs the worker step).

## Acceptance tests
- Given a `hubspot_writeback_job` with status=failed, when I POST `/admin/replay/hubspot-writeback/{job_id}`, then the worker step re-runs; success → status=sent, audit `hubspot_write.replayed`.
- Given an `integration_event` with `processed_at IS NULL` and `attempts >= MAX`, list surfaces it; replay pushes it back on the queue.
- Given a `notification` with status=failed, replay resets to pending with attempts=0.
- Non-SystemAdmin → 403 on every replay endpoint.
- Every replay writes audit.

## Data
- Reads existing tables; no new tables.

## Notes
- Blueprint §12 (DLQ with replay).
- Reuses Agent C (HubSpot intake), Agent M (notifications), Agent W (HubSpot writeback) machinery.
