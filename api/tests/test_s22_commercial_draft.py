"""S22 · server-persisted commercial draft (owner click-through root cause).

The Staffing & GM plan must survive reloads and be readable from every
surface. Drafts are mutable working state — GM versions stay immutable
and are created only by Save version. Concurrency: a stale writer 409s.
"""

from __future__ import annotations

import uuid

import pytest


async def _seed(session):
    from app.models.client import Client
    from app.models.opportunity import Opportunity
    from app.models.user import User

    owner = User(id=uuid.uuid4(), email=f"cd-{uuid.uuid4().hex[:6]}@smartek21.com",
                 name="Draft Owner", groups=["Delivery"])
    client = Client(id=uuid.uuid4(), name="Draft Client")
    session.add_all([owner, client])
    await session.flush()
    opp = Opportunity(id=uuid.uuid4(), client_id=client.id, owner_id=owner.id,
                      governance_status="Intake")
    session.add(opp)
    await session.commit()
    return opp


@pytest.mark.asyncio
async def test_draft_roundtrip_conflict_and_permissions(session, monkeypatch):
    import httpx

    from app.db import get_session
    from app.main import app as main_app

    monkeypatch.setenv("DEALGATE_ENV", "local")
    opp = await _seed(session)

    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    inputs = {"profile": "fixed_assignment", "staffing": [{"role": "Offshore consultant"}]}
    try:
        transport = httpx.ASGITransport(app=main_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            headers = {"X-Test-User": "cd@smartek21.com"}
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
            assert (await c.get(f"/delivery-model/{opp.id}/commercial/draft",
                                headers=headers)).status_code == 403

            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
            empty = await c.get(f"/delivery-model/{opp.id}/commercial/draft", headers=headers)
            assert empty.status_code == 200 and empty.json() == {"exists": False}

            put = await c.put(
                f"/delivery-model/{opp.id}/commercial/draft", headers=headers,
                json={"inputs": inputs, "sow_version_id": None, "expected_updated_at": None},
            )
            assert put.status_code == 200, put.text
            stamp = put.json()["updated_at"]

            got = await c.get(f"/delivery-model/{opp.id}/commercial/draft", headers=headers)
            body = got.json()
            assert body["exists"] is True
            assert body["inputs"]["staffing"][0]["role"] == "Offshore consultant"
            assert body["updated_at"] == stamp

            # Stale writer (older stamp) is refused — no silent overwrite.
            stale = await c.put(
                f"/delivery-model/{opp.id}/commercial/draft", headers=headers,
                json={"inputs": {"profile": "tm"}, "sow_version_id": None,
                      "expected_updated_at": "2020-01-01T00:00:00+00:00"},
            )
            assert stale.status_code == 409

            # Fresh stamp updates.
            ok = await c.put(
                f"/delivery-model/{opp.id}/commercial/draft", headers=headers,
                json={"inputs": {"profile": "tm", "staffing": []},
                      "sow_version_id": None, "expected_updated_at": stamp},
            )
            assert ok.status_code == 200

            # Discard, then a put that expected the old draft 409s.
            assert (await c.delete(f"/delivery-model/{opp.id}/commercial/draft",
                                   headers=headers)).status_code == 204
            assert (await c.get(f"/delivery-model/{opp.id}/commercial/draft",
                                headers=headers)).json() == {"exists": False}
            ghost = await c.put(
                f"/delivery-model/{opp.id}/commercial/draft", headers=headers,
                json={"inputs": inputs, "sow_version_id": None,
                      "expected_updated_at": ok.json()["updated_at"]},
            )
            assert ghost.status_code == 409
    finally:
        main_app.dependency_overrides.pop(get_session, None)
