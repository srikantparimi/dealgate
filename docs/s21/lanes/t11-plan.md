# T11 Connected Tracking Ownership

2026-10-02 21:55 UTC; base225a81d7c4a1e4a1eeff34fd25bfad7ec7d18237.
Requirement S21-13; original T11 and its conditions remain unchanged.

Backend worker: /root/s21_governance, branch s21/tracking-boundaries,
worktree /Users/srikanthparimi/OfficeApp/dealgate-s21-tracking-boundaries.
Exclusive ownership: routers/{deal_comments,next_actions,timeline}.py,
services/{deal_comment,next_action}.py, new services/tracking_access.py if needed,
new api/tests/test_s21_tracking_boundaries.py and lane tracking-boundaries.md.
Lead expanded ownership to existing test_deal_comment.py and test_next_action.py
for required-revision setup only; preserve every business assertion.
No migrations, model edits, UI, provider calls, deployment or retained DB writes.
Author red tests first. Reuse underlying deal authority, do not invent role policy.
Propose any policy uncertainty to lead before implementation.

Lead owns web/src/pages/v2/DealDetail.tsx, additive web/src/api/client.ts,
new web/src/pages/v2/DealTracking.tsx (bounded forms/list component),
focused UI tests, browser journey, separate-session PG proof, integration/reporting.
QA independent read-only assessment complete; review final connected boundaries.
Capacity22:03: ~667MiB free/~1GiB compressor permits second light read-only QA
review alongside backend author and lead. No concurrent heavy runtime/test processes.

Wire contract: comment/action rows expose an opaque `revision` string plus
capability flags `can_edit` (and comment `can_delete`). PATCH sends
`expected_revision`; absence is 428, stale is 409, never silent last-write-wins.
DELETE comment uses If-Match with the returned revision. Lock and reread current
row before comparing; authorization precedes mutation and token disclosure.
Revision must change for every actual mutation, including pin/unpin and same-title
status changes. Reuse current schema only if that guarantee is maintained; lead
orders any necessary migration. No audit event on a rejected write.
Rows expose resolved author_name for internal comments, retain source attribution.
Timeline must obey comment read rights and deal/fixture authority, and expose edits.
Global lists/client timelines must not leak inaccessible deals.

Proof: different roles and unrelated issued fixtures; add/edit/pin comment,
create/edit/complete action, reload latest activity, CRM note read-only/source,
escaped content, unauthorized writes and simultaneous independent PG sessions.
Synthetic CRM-note seed is explicitly not proof of connector ingestion.
