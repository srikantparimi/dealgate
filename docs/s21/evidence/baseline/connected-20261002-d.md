# Connected Local Journey: Passed

Tested revision `d25e1363657c22b2ec1e2cbf09cd93d5eddfaef7`, application
`a6c9e7c4df132f2e119b0c47c0d46aebb2910768`, 2026-10-02 18:49-18:50 UTC.
Session94568 finished. [Raw stdout](connected-20261002-d.log) includes the final
`connected_local_journey_passed` assertion and both exact S3 deletion receipts.
The shell used tee without pipefail: shell exit0 alone is NOT evidence; the
explicit final business assertion, lack of terminal traceback and cleanup are.
Future runs should use `bash -o pipefail -c 'COMMAND 2>&1 | tee UNIQUE_LOG'`.

Script: `scripts/s21_connected_journey.py`; setup: `scripts/s21_connected_setup.py`.
Exact environment/command and setup IDs are in the current Claude handoff.
Real ASGI application/SQLAlchemy PostgreSQL0061, real Bedrock and S3, separate
worker processes. Synthetic local identity and SES sink; no real CRM/Cognito,
email delivery, staging deployment or browser claim.

## Business Assertions

| Requirements / scenarios | Passed scope | Remaining whole-scope verification |
| --- | --- | --- |
| S21-07, S21-09, S21-12, DG-04, DG-06 / T17 | Server-issued fixture in authorized Pipeline list/detail, truthful local origin and null HubSpot ID; same Deal/client binding and real upload. | NDA/MSA semantics, empty-deal UI, names/counts everywhere, leak gate/route inventory, browser navigation and staging. |
| S21-05, S21-06, FC-09 / T17,T24 | Real extraction preserves two personal identities; five actual role decisions; signed bytes re-extracted and verified; accepted Delivery handoff. | Real roster/OOO/mail, other profiles, held-out ambiguous originals, OCR/attempt history and staging. |
| S21-15, S21-17, FC-02, FC-04 / T19,T21 | Two-location fixed-fee hybrid: US10000/4000 revenue/cost, India14000/6000; signed24000/cost10000; zero potential; same source/version and15months. Literal expectations independent of production output. | Other profiles, currencies, milestone/calendar edges and six-account preview. |
| FC-07, FC-08, FC-10 / T22,T23,T24 | Released project event and zero-person supply import produce review state; Delivery capability enrichment produces complete seven-head draft, US2/India5, probability1, September1 sourcing deadline. Old jobs/drafts unchanged; replay handles0 and does not duplicate current draft. | Probability/competing supply/continuity event breadth, disable/re-extract on this same source, notifications, load and staging. |
| FC-06, FC-12, CO-05 / T21,T25 | Same signed project's four financial bases, idempotent import, recognized12000.01 corrected11000.99; billed15000/cash8000/cost6000 remain distinct. Revision chain and original GM retained; schedule and baseline unchanged. | Unknown/zero/mixed currencies, matched actual-to-date union, all permissions/export/history breadth and staging. |

No whole requirement or compound scenario is closed by this subset. T17/T24
return from failed to pending because their observed failing constituent now
passes; the complete scenario assertions above remain outstanding.

## Persisted Identities And Recovery

- Tenant `s21-connected-d75f2b129e6a4290afce91933b1f00a8`.
- Client `26774a20-9f47-41f8-ab0a-5c124724fea2`.
- Deal `9df2917f-0a6a-4991-8ee0-d82eaf3ff305`.
- SOW version `d6045024-6280-4206-985e-354c2eba3ca7`.
- GM `b7aefb20-151d-4b02-a1e7-0a59208d251a`.
- Approval package `6f5483d0-89bc-446b-814a-aa33d7c0dee0`.
- Project `4dfcff0c-2f9d-41e6-932c-bf07ed6bb698`.
- Publication `d7dcf0f4-b8fb-472a-835b-4f5e58b75d89`, revision2.
- Sourcing draft `729ee93c-c2e0-471d-9ce7-a3494c1397e6`.

Owned uploaded and signed S3 objects/versions deleted; local retained DB rows
remain for audit. Do not reuse this tenant for a fresh-only script or restore
deleted document objects. Expiring grants are intentional, not permission bugs.
