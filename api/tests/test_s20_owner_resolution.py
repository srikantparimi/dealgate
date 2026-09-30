"""T04 · owner resolution across states (S20 · W5).

Per review + D2:
- deal sales owner   → HubSpot owner id, resolved via owner mirror
                       (archived owners included).
- client account owner → HubSpot company owner property, else "not set";
                       NEVER derived from a deal.
- local assignee     → DealGate user for actions/tasks only.

Display rules:
- unresolved source reference   → "Owner details unavailable".
- empty source                   → "Unassigned".

**Skeleton, xfail until W1 exposes the owner mirror.**

Assertions (one per test):
  1. active HubSpot owner resolves to their name.
  2. archived HubSpot owner still resolves (with archived=true marker).
  3. deal with source_owner_id set but no mirror row → "Owner details
     unavailable" (not "Unassigned").
  4. deal with source_owner_id NULL → "Unassigned".
  5. company account owner differs from every deal owner (D2: never
     overwritten by deal traversal).
  6. HubSpot owner id without a local DealGate user login is still a
     valid deal owner — a missing local login MUST NOT read as
     "missing CRM ownership".
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W1 owner mirror table with archived support", strict=False)
@pytest.mark.asyncio
async def test_active_owner_resolves_to_name(session):
    """
    Given: an opportunity whose source_owner_id points to an active
    HubSpot owner mirror row (`Sam Owner`).
    When:  list_opportunities() returns the row.
    Then:  row.owner_name == "Sam Owner"; row.owner_archived is False.
    """
    raise AssertionError("skeleton: implement once W1's owner mirror lands")


@pytest.mark.xfail(reason="depends on W1 owner mirror with archived support (D2)")
@pytest.mark.asyncio
async def test_archived_owner_still_resolves(session):
    """
    Given: an opportunity whose source_owner_id points to an archived
    HubSpot owner (person left the company).
    When:  list_opportunities() returns the row.
    Then:  row.owner_name == "Alex Retired"; row.owner_archived is True.
           The row is not dropped from the list.
    """
    raise AssertionError("skeleton: implement once W1's owner mirror lands")


@pytest.mark.xfail(reason="depends on W1 owner mirror table")
@pytest.mark.asyncio
async def test_unresolved_owner_reads_owner_details_unavailable(session):
    """
    Given: an opportunity whose source_owner_id references an id NOT
    in the owner mirror (out-of-sync).
    Then:  row.owner_display_state == "unresolved"; the SPA renders
           "Owner details unavailable" — never "Unassigned".
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 mirror")
@pytest.mark.asyncio
async def test_null_source_owner_reads_unassigned(session):
    """
    Given: an opportunity with source_owner_id IS NULL.
    Then:  row.owner_display_state == "unassigned".
           This is the only case that reads "Unassigned".
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 mirror and Client.account_owner_id column")
@pytest.mark.asyncio
async def test_company_account_owner_not_derived_from_deals(session):
    """
    Given: a client with three deals owned by three different people,
    and Client.account_owner_id set explicitly to a fourth person.
    When:  list_clients() returns the row.
    Then:  the account owner shown == the fourth person, not any of
           the deal owners. Removing `account_owner_id` renders
           "not set", not the modal deal owner. D2 forbids derivation
           from deals.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 mirror")
@pytest.mark.asyncio
async def test_hubspot_owner_without_local_login_still_valid(session):
    """
    Given: an opportunity with source_owner_id == a HubSpot owner who
    has NO DealGate user row (their email isn't in Cognito yet).
    Then:  row.owner_name shows the HubSpot owner name from the mirror
           (not blank, not "Unassigned"). A missing local login must
           not read as missing CRM ownership.
    """
    raise AssertionError("skeleton")
