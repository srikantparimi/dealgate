"""S23-PL2 B4 · resolve_viewer: the caller's effective HubSpot owner, read without writing."""

from __future__ import annotations

import uuid

import pytest

from app.auth import AuthUser
from app.models.user import User
from app.services.canonical_user import resolve_viewer
from app.services.hubspot_owners import HubspotOwner


def _actor(user: User) -> AuthUser:
    return AuthUser(user.id, user.email, user.name, ("Sales",))


@pytest.mark.asyncio
async def test_undecided_user_gets_the_exact_email_match(session):
    user = User(email="Pat@Example.test", name="Pat", groups=["Sales"])
    session.add_all([user, HubspotOwner(id="o1", email="pat@example.test", archived=False)])
    await session.flush()
    viewer = await resolve_viewer(session, _actor(user))
    assert (viewer.user_id, viewer.hubspot_owner_id, viewer.link) == (user.id, "o1", None)
    assert viewer.mine_available


@pytest.mark.asyncio
async def test_owner_linked_to_someone_else_is_not_an_email_match(session):
    owner_of = User(email="a@example.test", name="A", groups=["Sales"], hubspot_owner_id="o1", hubspot_owner_link="admin")
    undecided = User(email="b@example.test", name="B", groups=["Sales"])
    session.add_all([owner_of, undecided, HubspotOwner(id="o1", email="b@example.test", archived=False)])
    await session.flush()
    viewer = await resolve_viewer(session, _actor(undecided))
    assert viewer.hubspot_owner_id is None and not viewer.mine_available
    linked = await resolve_viewer(session, _actor(owner_of))
    assert (linked.hubspot_owner_id, linked.link) == ("o1", "admin")


@pytest.mark.asyncio
async def test_admin_unlink_and_archived_owner_and_unknown_caller(session):
    unlinked = User(email="c@example.test", name="C", groups=["Sales"], hubspot_owner_link="admin")
    archived_match = User(email="d@example.test", name="D", groups=["Sales"])
    session.add_all([
        unlinked, archived_match,
        HubspotOwner(id="o3", email="c@example.test", archived=False),
        HubspotOwner(id="o4", email="d@example.test", archived=True),
    ])
    await session.flush()
    # An admin decided "no owner": the email match is never used again.
    assert (await resolve_viewer(session, _actor(unlinked))).hubspot_owner_id is None
    # Archived owners are not matched automatically.
    assert (await resolve_viewer(session, _actor(archived_match))).hubspot_owner_id is None
    # A caller with no user row yet resolves to nothing, without writing one.
    stranger = AuthUser(uuid.uuid4(), "nobody@example.test", "Nobody", ("Sales",))
    assert (await resolve_viewer(session, stranger)).user_id is None
