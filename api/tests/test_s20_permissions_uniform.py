"""T27 · permissions uniform across UI/API/aggregates/search/export (S20 · W5).

Per review:
> Attempt unauthorized direct URLs, API decisions, salary reads,
> downloads and exports. Server denies access; role changes cannot
> self-grant CEO authority.

Per contract §8: permissions identical across UI, API, aggregates,
search, groups, exports, downloads. CRM ownership does not grant a
local approval role. Staff cost detail remains restricted.

**Skeleton — enumerates every mutating endpoint and every restricted
read; asserts 403 for wrong-role callers.**

Test cases (skeleton — expand as endpoints solidify):
  1. POST /approvals/{id}/finance as a `Delivery`-only user → 403.
  2. POST /ceo-exceptions as a non-CEO user → 403.
  3. GET /packages/{id}/staff-cost-detail as a Sales user → 403.
  4. GET /audit/*.csv as a non-audit-role user → 403.
  5. POST /release/{id} as a Sales user (even the deal owner) → 403.
  6. Groups/search returns rows a user has permission to see; the
     same query as a lower-role user returns strictly fewer or equal
     rows.
  7. Exports (CSV/PDF) obey the same permission set as list APIs.
  8. `cognito:groups` role change in the token cannot self-grant CEO
     — the server re-checks against Cognito on every request; a
     tampered token fails signature verification (A8).
"""

from __future__ import annotations

import pytest


_MUTATING_ENDPOINTS = [
    # (method, path, allowed_role, forbidden_role)
    ("POST", "/api/approvals/{id}/finance", "Finance", "Delivery"),
    ("POST", "/api/approvals/{id}/legal", "Legal", "Finance"),
    ("POST", "/api/ceo-exceptions", "CEO", "Delivery"),
    ("POST", "/api/release/{id}", "Delivery", "Sales"),
    ("POST", "/api/signature/send/{id}", "SalesLeader", "Sales"),
    ("GET", "/api/packages/{id}/staff-cost-detail", "Finance", "Sales"),
    ("GET", "/api/audit/export.csv", "Finance", "Sales"),
]


@pytest.mark.xfail(reason="skeleton; wire to a test client with role-partitioned tokens", strict=False)
@pytest.mark.parametrize("method,path,allowed,forbidden", _MUTATING_ENDPOINTS)
@pytest.mark.asyncio
async def test_wrong_role_gets_403(method, path, allowed, forbidden, session):
    """
    Given: an endpoint that allows `allowed` and forbids `forbidden`.
    When:  a token in group `forbidden` calls it.
    Then:  response is 403; error_code is "role_forbidden"; the
           allowed roles are listed in the payload.
           No side effect happens.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton; wire to Cognito token validator")
@pytest.mark.asyncio
async def test_forged_cognito_groups_are_rejected(session):
    """
    Given: a Cognito token whose `cognito:groups` claim has been
    edited to include "CEO" after signing.
    When:  it hits any endpoint.
    Then:  response is 401; the signature verification catches the
           tamper. Any endpoint that does NOT re-verify signatures
           on every request is a defect (contract §A8).
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton; wire to search endpoint")
@pytest.mark.asyncio
async def test_search_permissions_match_list_permissions(session):
    """
    Given: a client that is visible to `Delivery` but not `Sales`.
    When:  a Sales user searches for that client name.
    Then:  the search returns zero rows;
           the same search as Delivery returns the client.
           Permissions in search == permissions in list == permissions in export.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="skeleton; wire to export endpoints")
@pytest.mark.asyncio
async def test_export_obeys_same_permissions_as_list(session):
    """
    Given: a Sales user requests CSV export of the pipeline list.
    When:  they hit /api/pipeline/export.csv.
    Then:  the CSV contains exactly the rows the list API returned;
           NO privileged columns (staff cost detail, salary, private
           notes) appear even though the row is visible.
    """
    raise AssertionError("skeleton")
