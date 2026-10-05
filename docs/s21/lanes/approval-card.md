# T40 Approval Card Population

Branch `s21/approval-card-population`, baseline
`5a5c42c849ecb3807d0816beec62c5fd49bf6782`. Owned changes are the approval list
service/router, new independent test file, and this report. No transition,
migration, release authority, provider, infrastructure or shared database change.

## Contract And Implementation

`GET /approvals/packages?status=in_review` returns distinct current live SOW
packages in pending Delivery/HR, Finance/Legal or CEO-exception states. Rank all
nonvoided packages per SOW first, then filter pending states: an older pending
package cannot reappear behind a newer approved package. Exclude archived
SOW/Deal/client, missing parents, discarded/superseded versions and superseded
packages. Keep deterministic submitted-time/ID ordering and opportunity filtering.

Existing governance read-role, owner and assignment scope applies before paging.
Existing server-issued fixture validation additionally checks exact issued Deal,
participant/uploader, issuer/owner, environment/tenant and expiry. Counts and page
rows derive from one materialized authorized candidate population. No CRM-only
Pipeline predicate: ordinary local and legacy clientless business SOWs remain
eligible. Closed sales stage alone does not change package review state. Other
exact-status list semantics remain unchanged; no approval state is mutated.

## Local Evidence

Tests authored before production changes. While the heavy slot was held, the
implementation was authored without execution. Once granted, the new dispatch
branch was temporarily removed using a scoped patch so the unchanged old
status-equality path ran: **four failed, 14 passed**, session80406. Restore of
the branch then produced **18 passed**, session71511, exit0. No weakened tests,
skips or retries. No new dependency installation or shared generated files.

Command, from this tree's `api` directory:

```sh
env -u DEALGATE_POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest -p no:cacheprovider tests/test_s21_approval_card.py -q
```

Real HTTP/router/service and isolated SQLite assertions cover two SOWs under one
Deal, five reviewer assignments counting once, all three pending states,
draft/approved/released/rejected exclusions, newest-approved suppression,
nonvoided fallback, archive/discard/supersession, owner/reviewer/restricted users,
exact paginated identities/total/empty page, closed-stage/local/clientless records,
exact fixture versus unissued sibling, ordinary versus test users, invalid grants
and forged labels, plus unchanged existing exact-status behavior.

## Remaining Boundary

Lead owns Command Center/destination integration, PostgreSQL/browser fixtures and
the complete T40 business journey. These 18 cases do not close T40 or CO-04,
prove staging, or establish production-volume latency. Materializing and validating
the candidate population prioritizes exact authorization/count parity; its
existing provenance reads and projection cost require the separate load gate.
Runtime slot released immediately after the focused run; no process remains.

## Population Revision Follow-Up

An equal-count membership swap can evade total/duplicate guards during paging.
The canonical response now adds `population_revision`, SHA256 of its full ordered
authorized `(package_id, status, sow_version_id)` population and actor/read-scope/
opportunity context. Page size/index are deliberately not part of the revision.
An optional expected `population_revision` query rejects mismatch with HTTP409
and an explicit refresh instruction, including page1/card requests. No stored
snapshot, schema migration or approval write is introduced. Legacy status
responses add a nullable field; `list_packages` retains its tuple-two interface.
The explicit canonical helper returns rows/total/revision for the router.

Six new cases failed before implementation (session98041, 18 prior passes);
all **24 cases passed** with the fix (session99874, exit0), using the same isolated
command above. Assertions cover unchanged pages across page sizes, equal-count
outgoing/incoming package swaps on page1 and page2, pending status changes without
membership change, viewer/opportunity scope binding, empty populations and legacy
response compatibility. Lead owns carrying the token from card through board
pagination and explicit stale refresh. These local tests do not establish a
durable historical snapshot or replace the real browser/staging journey.
