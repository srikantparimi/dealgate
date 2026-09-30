"""T21 · material change invalidates approvals (S20 · W5).

Per review:
> Change price/scope/staffing after approval. Preserve history;
> invalidate affected approvals and prevent signature/release until
> resolved.

CLAUDE.md rule 4: "SOW, GM and approval records are immutable versions.
Never UPDATE them." So a material change is a NEW version, and
approvals against the previous version become non-authoritative for the
new version.

**Skeleton, xfail until W3 lands the revision-invalidation path.**

Test cases:
  1. Price change on an approved package creates a new version and
     invalidates every functional approval on the old version.
  2. Scope change on approved package → same rule.
  3. Staffing cost change (rate/quantity) on approved package → same
     rule.
  4. History preserved: querying the audit table shows the old version
     WITH the old approvals INTACT; a `superseded_by` link points to
     the new version.
  5. Signature endpoint refuses to send while any invalidated approval
     is outstanding.
  6. Release endpoint refuses until all functional approvers re-approve
     the new version.
"""

from __future__ import annotations

import pytest

MATERIAL_CHANGE_CASES = [
    ("price_change", "amount", "150000"),
    ("scope_change", "scope_text", "New: 12-month engagement, +2 developers"),
    ("staffing_cost_change", "role_rate", "185.00"),
]


@pytest.mark.xfail(
    reason="depends on W3 material-change revision + invalidation (T21)",
    strict=False,
)
@pytest.mark.parametrize("case,field,new_value", MATERIAL_CHANGE_CASES)
@pytest.mark.asyncio
async def test_material_change_bumps_version_and_invalidates(case, field, new_value, session):
    """
    Given: SOW package v1 with all four functional approvals.
    When:  a material change on `field` commits.
    Then:  package.version_number == 2;
           every approval on v1 has `superseded_at IS NOT NULL` and
           `superseded_reason == "material_change"`;
           the v1 records are NOT updated (immutability rule 4).
    """
    raise AssertionError(f"skeleton: {case}")


@pytest.mark.xfail(reason="depends on W3 signature gate")
@pytest.mark.asyncio
async def test_signature_refused_while_invalidated_approvals_outstanding(session):
    """
    Given: package after a material change; v2 has 3/4 re-approvals.
    When:  signature/send is called.
    Then:  server returns 409 reason "approvals_incomplete_on_current_version";
           payload lists the missing approver roles.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W7 release gate")
@pytest.mark.asyncio
async def test_release_refused_until_re_approval_complete(session):
    """
    Given: package v2 all re-approved but material change discovered
    late; another change bumps to v3.
    When:  release check runs.
    Then:  returns 409 reason "approvals_incomplete_on_current_version";
           re-approvals must land on v3.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W3 audit trail")
@pytest.mark.asyncio
async def test_history_preserves_old_approvals(session):
    """
    Given: package v1 approved, material change to v2.
    When:  we query audit_event for the package.
    Then:  v1 approvals are still present unchanged; there is a
           `revision_created` event; the v1 rows link to v2 via
           `superseded_by`. Immutability preserved (CLAUDE.md rule 4).
    """
    raise AssertionError("skeleton")
