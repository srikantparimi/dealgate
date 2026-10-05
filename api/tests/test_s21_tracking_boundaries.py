"""T11: real HTTP tracking authority, opaque revisions and attributed activity."""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from app.auth import current_user
from app.db import get_session
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.deal_comment import DealComment
from app.models.next_action import NextAction
from app.models.opportunity import Opportunity
from app.models.user import User
from app.routers.deal_comments import router as comments
from app.routers.next_actions import router as actions
from app.routers.timeline import router as timeline
from app.services.test_fixtures import create_fixture


@pytest.fixture
async def world(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "tracking-test")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    users = [User(email=f"{uuid.uuid4()}@example.test", name=name, groups=roles)
             for name, roles in [("Author", ["Sales"]), ("Other", ["Sales"]),
                                 ("Leader", ["SystemAdmin"]), ("Viewer", []),
                                 ("Fixture A", ["SystemAdmin", "officeapp-e2e"]),
                                 ("Fixture B", ["SystemAdmin", "officeapp-e2e"])]]
    session.add_all(users)
    account = Client(name="Tracking account")
    session.add(account)
    await session.flush()
    deal = Opportunity(name="Owned business", client_id=account.id, owner_id=users[0].id,
                       source="hubspot", hubspot_deal_id="synthetic-tracking-deal")
    session.add(deal)
    await session.flush()
    grants = [await create_fixture(session, actor_id=user.id, label="Tracking", reviewer_ids=[])
              for user in users[4:]]
    await session.commit()
    return users, account, deal, grants


async def request(session, actor, method, path, expected=200, **kwargs):
    app = FastAPI()
    for router in (comments, actions, timeline):
        app.include_router(router)
    app.dependency_overrides[current_user] = lambda: actor

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.request(method, path, **kwargs)
    assert result.status_code == expected, result.text
    return result.json() if result.content else None


async def count_audit(session):
    return await session.scalar(select(func.count()).select_from(AuditEvent))


@pytest.mark.asyncio
async def test_comment_revision_pin_aba_author_capabilities_and_conflict_has_no_audit(session, world):
    users, _, deal, _ = world
    row = await request(session, users[0], "POST", f"/deals/{deal.id}/comments", 201,
                        json={"body": "<script>plain text</script>"})
    assert row["author_name"] == "Author" and row["can_edit"] and row["can_delete"]
    assert row["body"] == "<script>plain text</script>"  # Transport remains plain text; UI escapes.
    path = f"/deal-comments/{row['id']}"
    count = await count_audit(session)
    await request(session, users[0], "PATCH", path, 428, json={"pinned": True})
    assert await count_audit(session) == count
    pinned = await request(session, users[0], "PATCH", path,
                           json={"pinned": True, "expected_revision": row["revision"]})
    assert pinned["edited_at"] and pinned["revision"] != row["revision"]
    unpinned = await request(session, users[0], "PATCH", path,
                             json={"pinned": False, "expected_revision": pinned["revision"]})
    assert unpinned["revision"] not in {row["revision"], pinned["revision"]}
    count = await count_audit(session)
    await request(session, users[0], "PATCH", path, 409,
                  json={"body": "stale overwrite", "expected_revision": row["revision"]})
    assert await count_audit(session) == count
    await request(session, users[0], "DELETE", path, 428)
    await request(session, users[0], "DELETE", path, 409, headers={"If-Match": row["revision"]})
    await request(session, users[0], "DELETE", path, 204, headers={"If-Match": unpinned["revision"]})


@pytest.mark.asyncio
async def test_action_status_revisions_and_assignment_options(session, world):
    users, _, deal, _ = world
    options = await request(session, users[0], "GET", f"/next-actions?opportunity_id={deal.id}")
    assert options["can_create"]
    assert {row["id"] for row in options["assignees"]} == {str(u.id) for u in users[:3]}
    action = await request(session, users[0], "POST", "/next-actions", 201,
        json={"opportunity_id": str(deal.id), "title": "Confirm scope", "assignee_user_id": str(users[0].id)})
    path = f"/next-actions/{action['id']}"
    assert action["can_edit"]
    await request(session, users[0], "PATCH", path, 428, json={"status": "complete"})
    updated = await request(session, users[0], "PATCH", path,
                            json={"status": "complete", "expected_revision": action["revision"]})
    assert updated["status"] == "complete" and updated["revision"] != action["revision"]
    count = await count_audit(session)
    await request(session, users[0], "PATCH", path, 409,
                  json={"title": "stale", "expected_revision": action["revision"]})
    assert await count_audit(session) == count
    assert (await request(session, users[0], "GET", path))["title"] == "Confirm scope"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["comments", "actions", "timeline"])
async def test_unrelated_deal_access_is_denied_before_tracking_details(session, world, kind):
    users, _, deal, _ = world
    if kind == "comments":
        foreign = world[3][0]["opportunity_id"]
        await request(session, users[1], "GET", f"/deals/{foreign}/comments", 404)
        await request(session, users[1], "POST", f"/deals/{foreign}/comments", 404, json={"body": "forbidden"})
    elif kind == "actions":
        foreign = world[3][0]["opportunity_id"]
        await request(session, users[1], "GET", f"/next-actions?opportunity_id={foreign}", 404)
        await request(session, users[1], "POST", "/next-actions", 404,
                      json={"opportunity_id": str(foreign), "title": "Forbidden", "assignee_user_id": str(users[1].id)})
    else:
        await request(session, users[3], "GET", f"/deals/{deal.id}/timeline", 403)


@pytest.mark.asyncio
async def test_global_actions_and_client_timeline_do_not_leak_other_fixture(session, world):
    users, _, _, grants = world
    for actor, grant in zip(users[4:], grants):
        await request(session, actor, "POST", f"/deals/{grant['opportunity_id']}/comments", 201,
                      json={"body": f"private {actor.name}"})
        await request(session, actor, "POST", "/next-actions", 201,
                      json={"opportunity_id": str(grant["opportunity_id"]), "title": actor.name,
                            "assignee_user_id": str(actor.id)})
    data = await request(session, users[4], "GET", "/next-actions")
    assert [r["title"] for r in data["items"]] == [users[4].name]
    foreign = await request(session, users[4], "GET", f"/clients/{grants[1]['client_id']}/timeline")
    assert foreign["items"] == []
    own = await request(session, users[4], "GET", f"/clients/{grants[0]['client_id']}/timeline")
    assert any("private Fixture A" in r["body"] for r in own["items"])
    business = await request(session, users[2], "GET", "/next-actions")
    assert business["items"] == []


@pytest.mark.asyncio
async def test_direct_action_and_history_cannot_bypass_deal_access(session, world):
    users, _, _, grants = world
    action = await request(session, users[4], "POST", "/next-actions", 201,
        json={"opportunity_id": str(grants[0]["opportunity_id"]), "title": "Owned", "assignee_user_id": str(users[4].id)})
    path = f"/next-actions/{action['id']}"
    for suffix in ("", "/events"):
        await request(session, users[5], "GET", path + suffix, 404)
    await request(session, users[5], "PATCH", path, 404,
                  json={"status": "complete", "expected_revision": action["revision"]})


@pytest.mark.asyncio
async def test_latest_and_timeline_reflect_edits_with_author_and_source(session, world):
    users, _, deal, _ = world
    old = await request(session, users[0], "POST", f"/deals/{deal.id}/comments", 201, json={"body": "Original"})
    await request(session, users[0], "POST", f"/deals/{deal.id}/comments", 201, json={"body": "Newer"})
    await request(session, users[0], "PATCH", f"/deal-comments/{old['id']}",
                  json={"body": "Edited original", "expected_revision": old["revision"]})
    data = await request(session, users[0], "GET", f"/deals/{deal.id}/comments")
    assert data["latest"]["id"] == old["id"] and data["can_create"]
    activity = await request(session, users[0], "GET", f"/deals/{deal.id}/timeline")
    edited = next(r for r in activity["items"] if str(r["entity_id"]) == old["id"])
    assert edited["kind"] == "edited" and edited["comment_source"] == "internal"
    assert edited["actor_name"] == "Author" and "Edited original" in edited["body"]


@pytest.mark.asyncio
async def test_comment_read_policy_also_applies_to_timeline_and_crm_is_readonly(session, world):
    users, _, deal, _ = world
    note = DealComment(opportunity_id=deal.id, body="CRM source", source="hubspot_note",
                       hubspot_note_id="synthetic-note", author_name_fallback="CRM author",
                       created_at=datetime.now(UTC))
    session.add(note)
    await session.commit()
    data = await request(session, users[0], "GET", f"/deals/{deal.id}/comments")
    row = data["items"][0]
    assert row["author_name"] == "CRM author" and not row["can_edit"] and not row["can_delete"]
    await request(session, users[0], "PATCH", f"/deal-comments/{note.id}", 409,
                  json={"body": "writeback", "expected_revision": row["revision"]})
    deal.owner_id = users[3].id
    await session.commit()
    assert (await request(session, users[3], "GET", f"/deals/{deal.id}/comments"))["items"] == []
    await request(session, users[3], "GET", f"/deals/{deal.id}/timeline", 403)


@pytest.mark.asyncio
async def test_visible_business_records_do_not_grant_mutation_or_fixture_assignment(session, world):
    users, _, deal, _ = world
    comment = await request(session, users[0], "POST", f"/deals/{deal.id}/comments", 201, json={"body": "Owned"})
    other = await request(session, users[1], "GET", f"/deals/{deal.id}/comments")
    assert not other["items"][0]["can_edit"] and not other["items"][0]["can_delete"]
    await request(session, users[1], "PATCH", f"/deal-comments/{comment['id']}", 403,
                  json={"body": "Forbidden"})
    await request(session, users[1], "DELETE", f"/deal-comments/{comment['id']}", 403)
    action = await request(session, users[0], "POST", "/next-actions", 201,
        json={"opportunity_id": str(deal.id), "title": "Owned", "assignee_user_id": str(users[0].id)})
    assert not (await request(session, users[1], "GET", f"/next-actions/{action['id']}"))["can_edit"]
    await request(session, users[1], "PATCH", f"/next-actions/{action['id']}", 403,
                  json={"status": "complete"})
    before = await count_audit(session)
    await request(session, users[0], "POST", "/next-actions", 403,
        json={"opportunity_id": str(deal.id), "title": "Forbidden", "assignee_user_id": str(users[4].id)})
    assert await count_audit(session) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["comment", "action"])
async def test_locked_reread_rejects_stale_identity_map(session, world, kind):
    users, _, deal, _ = world
    if kind == "comment":
        row = await request(session, users[0], "POST", f"/deals/{deal.id}/comments", 201, json={"body": "Old"})
        model, path, value, patch = DealComment, f"/deal-comments/{row['id']}", {"body": "Concurrent"}, {"body": "Lost update"}
    else:
        row = await request(session, users[0], "POST", "/next-actions", 201,
            json={"opportunity_id": str(deal.id), "title": "Old", "assignee_user_id": str(users[0].id)})
        model, path, value, patch = NextAction, f"/next-actions/{row['id']}", {"status": "in_progress"}, {"status": "complete"}
    cached = await session.get(model, uuid.UUID(row["id"]))
    await session.execute(update(model).where(model.id == cached.id).values(**value)
                          .execution_options(synchronize_session=False))
    assert (cached.body if kind == "comment" else cached.status) == ("Old" if kind == "comment" else "open")
    before = await count_audit(session)
    await request(session, users[0], "PATCH", path, 409,
                  json={**patch, "expected_revision": row["revision"]})
    assert await count_audit(session) == before
    assert (cached.body if kind == "comment" else cached.status) == ("Concurrent" if kind == "comment" else "in_progress")


@pytest.mark.asyncio
async def test_unissued_sibling_hidden_from_client_timeline_and_grant_assignees(session, world):
    users, _, _, grants = world
    sibling = Opportunity(name="Unissued sibling", client_id=grants[0]["client_id"],
                          owner_id=users[4].id, source="sow_upload")
    session.add(sibling)
    await session.flush()
    session.add(DealComment(opportunity_id=sibling.id, author_id=users[4].id,
                            body="Never disclosed", source="internal"))
    await session.commit()
    data = await request(session, users[4], "GET", f"/clients/{grants[0]['client_id']}/timeline")
    assert data["items"] == []
    await request(session, users[4], "GET", f"/deals/{sibling.id}/comments", 404)
    options = await request(session, users[4], "GET", f"/next-actions?opportunity_id={grants[0]['opportunity_id']}")
    assert options["assignees"] == [{"id": str(users[4].id), "name": users[4].name}]
