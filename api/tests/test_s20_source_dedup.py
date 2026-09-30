"""T34 · source-event-id dedupe (S20 · W5).

Per D7 + review A4:
> Dedupe key = HubSpot source event id (or documented composite) with DB
> uniqueness guard. Record + audit + outbox committed atomically before
> SQS ack.

Retries of one HubSpot event can arrive as DIFFERENT queue messages.
Idempotent row upserts alone do not prevent duplicate audit entries,
tasks or notices. The DB uniqueness constraint on
`(source, source_event_id)` is the enforcement point.

**Skeleton, xfail until W1 lands the dedupe key.**

Test cases:
  1. Same source event id delivered as two SQS messages → exactly ONE
     business effect (one row change, one audit row, one outbox row).
     Both messages get acked.
  2. Retry after commit but before SQS ack (worker crash between DB
     commit and delete-message) → the second delivery sees the row
     already exists via unique constraint, acks, no double audit.
  3. Two DIFFERENT source event ids that both touch the same
     opportunity are BOTH applied (dedup is per-event, not per-row).
  4. Outbox row and audit row committed in the SAME transaction as
     the mirror row change; a partial commit is not visible.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W1 (source, source_event_id) unique constraint (D7)", strict=False)
@pytest.mark.asyncio
async def test_same_event_delivered_twice_yields_one_effect(session):
    """
    Given: HubSpot event id "evt-100" delivered as sqs-msg-A and later
    as sqs-msg-B.
    When:  both are processed.
    Then:  exactly one opportunity row change;
           exactly one audit_event row;
           exactly one outbox row;
           both SQS messages get acked.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 crash-safety (A4)")
@pytest.mark.asyncio
async def test_retry_after_commit_before_ack_is_idempotent(session):
    """
    Given: the worker committed the DB txn for "evt-101" but crashed
    before deleting the SQS message. On restart, the same message is
    re-delivered.
    When:  the second attempt runs.
    Then:  the DB unique constraint catches it; the handler treats
           this as `already_processed`; ONE audit row exists.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 dedupe scope (per-event, not per-row)")
@pytest.mark.asyncio
async def test_two_different_events_on_same_row_both_apply(session):
    """
    Given: opportunity O; events "evt-A" and "evt-B" both target O.
    Then:  both apply; two audit rows; the final state reflects the
           second event (or the merge, if the handler defines one).
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 atomic mirror+audit+outbox commit")
@pytest.mark.asyncio
async def test_partial_commit_is_never_visible(session):
    """
    Given: the audit insert fails (simulated).
    When:  the transaction rolls back.
    Then:  the mirror row change is also rolled back;
           the outbox row is not present; the SQS message is NOT
           acked (so redelivery retries the whole txn).
    """
    raise AssertionError("skeleton")
