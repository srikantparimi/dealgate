"""T18 · GM incomplete inputs → Not assessed (S20 · W5).

Per review:
> Missing rate, cost, currency, allocation or revenue basis stays
> incomplete; no false zero, healthy risk result or Finance approval.

Per contract §1: "Unavailable GM cannot yield No blockers." A missing
input MUST render as `Not assessed`, not zero-implies-approved.

**Skeleton — assertions target the gm assessment surface.**

Test cases:
  1. rate missing on any role → assessment status "not_assessed".
  2. cost missing → "not_assessed".
  3. currency missing → "not_assessed".
  4. allocation missing → "not_assessed".
  5. revenue basis missing → "not_assessed".
  6. Finance approval endpoint refuses a `not_assessed` package (server
     enforces; disabled button is not a control — §0.5 + §8).
  7. Command center attention/risk metric for this package is
     `unavailable` — NEVER "no blockers".
"""

from __future__ import annotations

import pytest


_MISSING_INPUT_CASES = [
    ("rate_missing", "rate"),
    ("cost_missing", "cost"),
    ("currency_missing", "currency"),
    ("allocation_missing", "allocation"),
    ("revenue_basis_missing", "revenue_basis"),
]


@pytest.mark.xfail(reason="skeleton; wire to gm.assess()", strict=False)
@pytest.mark.parametrize("case,input_field", _MISSING_INPUT_CASES)
def test_missing_input_yields_not_assessed(case, input_field):
    """
    Given: staffing sheet with `input_field` missing on one role.
    When:  gm.assess(sheet).
    Then:  result.status == "not_assessed";
           result.reason names `input_field`;
           result.margin is None (NEVER Decimal("0")).
    """
    raise AssertionError(f"skeleton: {case}")


@pytest.mark.xfail(reason="skeleton; wire to /approvals/{package_id}/finance")
@pytest.mark.asyncio
async def test_finance_approval_rejects_not_assessed_package(session):
    """
    Given: package whose GM assessment is `not_assessed`.
    When:  a Finance user POSTs /approvals/{package_id}/finance
    with decision=approve.
    Then:  server returns 409 with reason "gm_not_assessed".
           No approval row is created. Audit event NOT emitted.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton; asserts Command center attention render")
@pytest.mark.asyncio
async def test_command_center_reports_unavailable_not_zero(session):
    """
    Given: opportunity with `not_assessed` GM.
    When:  Command center metrics endpoint runs.
    Then:  attention.margin_risk == "unavailable" (string), NOT 0.
           The row is counted separately in unknown_bucket per §3
           response envelope.
    """
    raise AssertionError("skeleton")
