"""T39: exact authorized Watching population, independent of group multiplicity."""
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth import current_user
from app.db import get_session
from app.models.watchlist import WatchedItem
from app.routers.watchlist import router
from tests.test_s21_pipeline_fixture_projection import projected  # noqa: F401


@pytest.fixture
async def watching_client(session, projected):
    people, *_ = projected
    app = FastAPI()
    app.include_router(router)
    from app.routers.pipeline import router as pipeline_router
    app.include_router(pipeline_router)
    app.dependency_overrides[current_user] = lambda: people[0]
    async def database():
        yield session
    app.dependency_overrides[get_session] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://watching") as client:
        yield client


async def test_watch_rejects_inaccessible_and_unknown_subjects(watching_client, projected):
    _, _, _, sibling, crm = projected
    for item in (sibling.id, crm.id, uuid.uuid4()):
        response = await watching_client.post("/watchlist", json={"kind": "opportunity", "item_id": str(item)})
        assert response.status_code == 404, response.text


async def test_hidden_stale_watch_does_not_leak_identity_or_inflate_counts(session, watching_client, projected):
    people, _, local, _, crm = projected
    session.add_all([WatchedItem(user_id=people[0].id, kind="opportunity", item_id=item)
                     for item in (local.id, crm.id)])
    await session.commit()
    response = await watching_client.get("/watchlist")
    assert response.status_code == 200
    result = response.json()
    assert [r["item_id"] for r in result["items"]] == [str(local.id)]
    assert result["counts"] == {"opportunity": 1, "client": 0}
    assert result["matching_deal_count"] == 1


async def test_watch_client_and_deal_are_one_distinct_matching_deal(watching_client, projected):
    _, _, local, _, _ = projected
    for kind, item in (("opportunity", local.id), ("client", local.client_id)):
        response = await watching_client.post("/watchlist", json={"kind": kind, "item_id": str(item)})
        assert response.status_code == 201
    result = (await watching_client.get("/watchlist")).json()
    assert result["matching_deal_count"] == 1
    for kind, item in (("opportunity", local.id), ("client", local.client_id)):
        assert (await watching_client.delete("/watchlist", params={"kind": kind, "item_id": str(item)})).status_code == 204
    result = (await watching_client.get("/watchlist")).json()
    assert result["items"] == [] and result["matching_deal_count"] == 0


async def test_nonreader_cannot_list_or_add_watch(watching_client, projected):
    people, _, local, _, _ = projected
    people[0].groups = []
    assert (await watching_client.get("/watchlist")).status_code == 403
    assert (await watching_client.post("/watchlist", json={
        "kind": "opportunity", "item_id": str(local.id)})).status_code == 403


async def test_fixture_scope_does_not_revalidate_unrelated_viewers_grants(session, projected, monkeypatch):
    from app.audit import append_audit
    from app.services import test_fixtures
    from app.services.hubspot_pipeline import PipelineFilters, scope_pipeline_filters
    people, _, local, _, _ = projected
    for _ in range(12):
        await append_audit(session, actor_id=people[2].id, action=test_fixtures.ISSUED,
            entity="client", entity_id=str(uuid.uuid4()), before=None,
            after={"participant_ids": [str(people[2].id)]})
    calls = []
    original = test_fixtures.account_scope
    async def observed(session, client_id, **kwargs):
        calls.append(client_id)
        return await original(session, client_id, **kwargs)
    monkeypatch.setattr(test_fixtures, "account_scope", observed)
    filters = await scope_pipeline_filters(session, people[0], PipelineFilters())
    assert filters.authorized_fixture_opportunity_ids == (local.id,)
    assert set(calls) == {local.client_id}


async def test_watching_client_group_preserves_only_authorized_exact_deal(session, watching_client, projected):
    from app.models.tracking_group import TrackingGroup, TrackingGroupMember
    people, _, local, _, crm = projected
    group = TrackingGroup(owner_id=people[0].id, name="Client watch intersection", member_kind="client")
    session.add(group)
    await session.flush()
    session.add_all([TrackingGroupMember(group_id=group.id, member_id=item)
                     for item in (local.client_id, crm.client_id)])
    session.add_all([WatchedItem(user_id=people[0].id, kind="opportunity", item_id=item)
                     for item in (local.id, crm.id)])
    await session.commit()
    response = await watching_client.get("/pipeline/opportunities", params={"watching": "true", "group": str(group.id)})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total"] == 1
    assert [row["opportunity_id"] for row in result["items"]] == [str(local.id)]
