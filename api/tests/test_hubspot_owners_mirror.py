"""S20 W1 D2 · owner mirror acceptance.

Covers the T04 / T31 shape from `docs/reports/s20/contracts.md`:
- active + archived owners both land in the mirror.
- Repeat runs are idempotent (unchanged count grows).
- A previously-active owner that becomes archived flips the flag.
- Read-side resolver returns the row for a raw HubSpot owner id, including
  archived rows.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.hubspot import HubSpotClient, StubHubSpotClient
from app.services.hubspot_owners import (
    HubspotOwner,
    resolve_owner_by_id,
    sync_owner_mirror,
)
from app.services.sync_status import touch_source  # noqa: F401 - side-effect import


class _OwnersStubClient(StubHubSpotClient):
    """Stub with a controllable owners endpoint (real one goes through _get)."""

    def __init__(
        self,
        *,
        active: list[dict[str, Any]] | None = None,
        archived: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self._active = active or []
        self._archived = archived or []
        self.get_calls: list[dict[str, Any]] = []

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:  # noqa: SLF001
        self.get_calls.append({"path": path, "params": dict(params or {})})
        if path == "/crm/v3/owners":
            wants_archived = str((params or {}).get("archived", "false")).lower() == "true"
            data = self._archived if wants_archived else self._active
            return {"results": data}
        raise KeyError(path)


def _owner(id_: str, *, email: str, first: str, last: str, user_id: str | None = None) -> dict:
    row: dict[str, Any] = {
        "id": id_,
        "email": email,
        "firstName": first,
        "lastName": last,
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-02T00:00:00Z",
    }
    if user_id is not None:
        row["userId"] = user_id
    return row


@pytest_asyncio.fixture
async def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def test_owner_mirror_ingests_active_and_archived(factory):
    stub = _OwnersStubClient(
        active=[_owner("101", email="a@x.com", first="Ada", last="Lovelace")],
        archived=[
            _owner("102", email="c@x.com", first="Charles", last="Babbage", user_id="9902"),
        ],
    )
    async with factory() as s:
        counts = await sync_owner_mirror(s, stub)
        await s.commit()
    assert counts.active_seen == 1
    assert counts.archived_seen == 1
    assert counts.inserted == 2
    assert counts.updated == 0
    assert counts.unchanged == 0

    async with factory() as s:
        rows = (await s.execute(select(HubspotOwner))).scalars().all()
    by_id = {r.id: r for r in rows}
    assert by_id["101"].archived is False
    assert by_id["101"].email == "a@x.com"
    assert by_id["101"].first_name == "Ada"
    assert by_id["102"].archived is True
    assert by_id["102"].email == "c@x.com"
    assert by_id["102"].user_id == "9902"


async def test_owner_mirror_is_idempotent_on_repeat(factory):
    stub = _OwnersStubClient(
        active=[_owner("101", email="a@x.com", first="Ada", last="Lovelace")],
        archived=[],
    )
    async with factory() as s:
        first = await sync_owner_mirror(s, stub)
        await s.commit()
    assert first.inserted == 1

    async with factory() as s:
        second = await sync_owner_mirror(s, stub)
        await s.commit()
    assert second.inserted == 0
    assert second.updated == 0
    assert second.unchanged == 1


async def test_owner_mirror_updates_when_owner_transitions_to_archived(factory):
    active_owner = _owner("101", email="a@x.com", first="Ada", last="Lovelace")
    stub = _OwnersStubClient(active=[active_owner], archived=[])
    async with factory() as s:
        await sync_owner_mirror(s, stub)
        await s.commit()

    # Portal deactivates owner 101 → it now appears in the archived list.
    stub._active = []
    stub._archived = [active_owner]
    async with factory() as s:
        counts = await sync_owner_mirror(s, stub)
        await s.commit()
    assert counts.updated == 1

    async with factory() as s:
        row = await resolve_owner_by_id(s, "101")
    assert row is not None
    assert row.archived is True
    assert row.email == "a@x.com"  # D2 preserves the identity even when archived


async def test_resolve_owner_by_id_returns_none_for_unknown(factory):
    stub = _OwnersStubClient()
    async with factory() as s:
        await sync_owner_mirror(s, stub)
        await s.commit()
    async with factory() as s:
        assert await resolve_owner_by_id(s, "no-such-owner") is None
