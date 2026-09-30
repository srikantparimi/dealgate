"""T23 · release authorization (S20 · W5).

Per review:
> Verify executed terms and required conditions; Delivery accepts.
> Create/link project once; CRM Closed Won alone cannot authorize
> release.

Internal review signoff, client execution and delivery acceptance are
three distinct events (review §"State changes must be enforced on the
server"). All three must be exercised.

**Skeleton, xfail until W7 lands the release path.**

Test cases:
  1. CRM Closed Won alone → release refused; 409 reason
     "internal_signoff_missing".
  2. Internal signoff present + CRM Closed Won → still refused;
     reason "executed_document_missing".
  3. All three: internal signoff + executed doc + delivery accept →
     release authorized; project created exactly once.
  4. Retry of release after success → idempotent; project not created
     twice.
  5. Executed document with materially different terms → release
     refused; reason "executed_terms_diverge"; audit event references
     the divergent fields.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W7 release gate", strict=False)
@pytest.mark.asyncio
async def test_crm_closed_won_alone_refuses_release(session):
    """
    Given: package with is_closed_won=True but no internal signoff,
    no executed document, no delivery acceptance.
    When:  POST /release/{package_id}.
    Then:  409 reason "internal_signoff_missing".
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W7 release gate")
@pytest.mark.asyncio
async def test_internal_signoff_alone_still_refuses(session):
    """
    Given: internal signoff + CRM Closed Won but no executed doc.
    Then:  release returns 409 reason "executed_document_missing".
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W7 release + project provisioning")
@pytest.mark.asyncio
async def test_all_three_gates_pass_creates_project_once(session):
    """
    Given: internal signoff + executed doc + delivery acceptance.
    When:  POST /release/{package_id}.
    Then:  201; project created with provenance to (deal_id, package_id).
           A second POST returns 200 + the same project id (idempotent).
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W7 executed-terms diff check (T22)")
@pytest.mark.asyncio
async def test_executed_document_diverging_terms_refused(session):
    """
    Given: approved package at $100k; executed document at $85k.
    When:  release check runs.
    Then:  409 reason "executed_terms_diverge";
           audit event lists field="amount", approved=100000, executed=85000.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W7 idempotency guard")
@pytest.mark.asyncio
async def test_release_retry_is_idempotent(session):
    """
    Given: released package with a project already provisioned.
    When:  the client retries the release call (network hiccup).
    Then:  200 with the same project id;
           the audit table shows ONE `released` event, not two.
    """
    raise AssertionError("skeleton")
