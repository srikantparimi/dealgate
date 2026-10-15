"""S23-PL2 pre-merge review (R2) — the HubSpot owner link never fails a sign-in or the deal sync.

- Sign-in (``link_by_email``): when another session links the same owner first
  (``ux_user_hubspot_owner``) or the owner sync's bulk link deadlocks with the
  sign-in, the sign-in carries on unlinked. The user row is loaded again after
  the savepoint rollback, so the caller never reads an expired row (which was a
  MissingGreenlet 500).
- Owner sync (``link_all_by_email``): runs after the owner mirror has committed,
  in its own transaction. A conflict or a deadlock is logged and nothing is
  linked this run; the mirror stays saved, the deals still sync, and the next
  run links.

The SQLite tests put the failure exactly where PostgreSQL raises it. The
Postgres-gated tests reproduce the real races with two connections.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth import AuthUser
from app.db import get_session
from app.integrations.hubspot import StubHubSpotClient
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services import hubspot_backfill, hubspot_owners
from app.services.canonical_user import canonical_actor
from app.services.hubspot_backfill import run_backfill
from app.services.hubspot_owners import HubspotOwner, link_all_by_email, link_by_email

REP = "rita.rep@example.test"
AS_REP = {"X-Test-User": REP}
_PG_URL = os.environ.get("DEALGATE_POSTGRES_URL")
needs_postgres = pytest.mark.skipif(not _PG_URL, reason="requires postgres; set DEALGATE_POSTGRES_URL to run")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    monkeypatch.delenv("SALES_LEADER_EMAIL", raising=False)


@pytest_asyncio.fixture
async def factory(fk_engine):
    return async_sessionmaker(fk_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def sync_factory(savepoint_engine):
    # The backfill's per-deal savepoints and the bulk link's savepoint behave as on PostgreSQL.
    return async_sessionmaker(savepoint_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def api(factory):
    async def _session():
        async with factory() as s:
            yield s

    main_app.dependency_overrides[get_session] = _session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main_app, raise_app_exceptions=False), base_url="http://t"
        ) as client:
            yield client
    finally:
        main_app.dependency_overrides.pop(get_session, None)


def _deadlock() -> OperationalError:
    return OperationalError("SELECT pg_advisory_xact_lock(42424242)", {}, Exception("deadlock detected"))


async def _user(factory, user_id: uuid.UUID) -> User:
    async with factory() as s:
        return await s.get(User, user_id)


async def _linked_audits(factory) -> list[str]:
    async with factory() as s:
        return list((await s.scalars(
            select(AuditEvent.entity_id).where(AuditEvent.action == "user.hubspot_owner_linked"))).all())


async def _rep_and_owner(factory) -> uuid.UUID:
    """A HubSpot-created rep (fresh uuid4, no groups) and the active owner with the rep's email."""
    async with factory() as s:
        rep = User(id=uuid.uuid4(), email=REP, name="Rita Rep", groups=[])
        s.add_all([rep, HubspotOwner(id="o-rep", email="Rita.Rep@Example.test", first_name="Rita",
                                     last_name="Rep", archived=False)])
        await s.commit()
        return rep.id


# --- sign-in -------------------------------------------------------------------------------------------------


async def test_a_sign_in_whose_owner_is_linked_elsewhere_meanwhile_carries_on_unlinked(api, factory, monkeypatch):
    rep_id = await _rep_and_owner(factory)
    async with factory() as s:
        other = User(id=uuid.uuid4(), email="r.rep@example.test", name="Rita (second row)", groups=[])
        s.add(other)
        await s.commit()
        other_id = other.id
    real_apply = hubspot_owners._apply_email_link

    async def linked_elsewhere_meanwhile(session, user, owner_id, **kwargs):
        # Another session links this owner to a different row after link_by_email checked it was
        # free: the rep's write now violates ux_user_hubspot_owner.
        await session.execute(update(User).where(User.id == other_id)
                              .values(hubspot_owner_id=owner_id, hubspot_owner_link="admin"))
        await real_apply(session, user, owner_id, **kwargs)

    monkeypatch.setattr(hubspot_owners, "_apply_email_link", linked_elsewhere_meanwhile)
    response = await api.get("/me", headers=AS_REP)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(rep_id)
    assert response.json()["email"] == REP
    rep = await _user(factory, rep_id)
    assert (rep.hubspot_owner_id, rep.hubspot_owner_link) == (None, None)
    assert await _linked_audits(factory) == []


async def test_a_sign_in_that_deadlocks_with_the_owner_sync_carries_on_unlinked(api, factory, monkeypatch):
    rep_id = await _rep_and_owner(factory)
    real_audit = hubspot_owners.append_audit
    calls: list[str] = []

    async def deadlock_once(session, **kwargs):
        # The rep's row is already updated inside the savepoint; the audit lock wait is the one
        # PostgreSQL picks as the deadlock victim.
        calls.append(kwargs["entity_id"])
        if len(calls) == 1:
            raise _deadlock()
        return await real_audit(session, **kwargs)

    monkeypatch.setattr(hubspot_owners, "append_audit", deadlock_once)
    response = await api.get("/me", headers=AS_REP)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(rep_id)
    rep = await _user(factory, rep_id)
    assert (rep.hubspot_owner_id, rep.hubspot_owner_link) == (None, None)

    # The race is over: the next sign-in links.
    assert (await api.get("/me", headers=AS_REP)).status_code == 200
    rep = await _user(factory, rep_id)
    assert (rep.hubspot_owner_id, rep.hubspot_owner_link) == ("o-rep", "email")
    assert await _linked_audits(factory) == [str(rep_id)]


# --- the owner sync --------------------------------------------------------------------------------------------


def _owner(owner_id: str, email: str, first: str) -> dict:
    return {"id": owner_id, "email": email, "firstName": first, "lastName": "Rep", "archived": False}


def _deal(deal_id: str) -> dict:
    return {"id": deal_id, "properties": {
        "dealname": f"Deal {deal_id}", "dealstage": "qualifiedtobuy", "pipeline": "default", "amount": "1000",
        "deal_currency_code": "USD", "closedate": "2026-12-31", "hs_lastmodifieddate": "2026-10-13T12:00:00Z"}}


async def _undecided_pair(sync_factory) -> tuple[uuid.UUID, uuid.UUID]:
    async with sync_factory() as s:
        now = datetime.now(UTC)
        ann = User(id=uuid.uuid4(), email="ann.a@example.test", name="Ann", groups=[],
                   created_at=now - timedelta(minutes=2))
        bob = User(id=uuid.uuid4(), email="bob.b@example.test", name="Bob", groups=[],
                   created_at=now - timedelta(minutes=1))
        s.add_all([ann, bob])
        await s.commit()
        return ann.id, bob.id


def _stub() -> StubHubSpotClient:
    return StubHubSpotClient(deals={"d1": _deal("d1")}, owners={
        "o-ann": _owner("o-ann", "Ann.A@example.test", "Ann"), "o-bob": _owner("o-bob", "bob.b@example.test", "Bob")})


async def test_a_deadlocked_owner_link_never_fails_the_deal_sync(sync_factory, monkeypatch):
    ann_id, bob_id = await _undecided_pair(sync_factory)
    real_audit = hubspot_owners.append_audit
    calls: list[str] = []

    async def deadlock_on_bob(session, **kwargs):
        # Ann is linked (the sync now holds the audit lock); Bob signs in at that moment.
        calls.append(kwargs["entity_id"])
        if kwargs["entity_id"] == str(bob_id):
            raise _deadlock()
        return await real_audit(session, **kwargs)

    monkeypatch.setattr(hubspot_owners, "append_audit", deadlock_on_bob)
    counts = await run_backfill(_stub(), session_factory=sync_factory)
    assert counts.fatal_error is None, counts.fatal_error
    assert counts.scan_completed and counts.deals_written == 1
    assert calls == [str(ann_id), str(bob_id)]
    async with sync_factory() as s:
        # The owner mirror committed before the link ran; the deal synced.
        assert set((await s.scalars(select(HubspotOwner.id))).all()) == {"o-ann", "o-bob"}
        assert (await s.scalar(select(func.count()).select_from(Opportunity))) == 1
    # Nothing was linked this run (one batch, one savepoint).
    for user_id in (ann_id, bob_id):
        user = await _user(sync_factory, user_id)
        assert (user.hubspot_owner_id, user.hubspot_owner_link) == (None, None)

    # The next run links both.
    monkeypatch.setattr(hubspot_owners, "append_audit", real_audit)
    counts = await run_backfill(_stub(), session_factory=sync_factory)
    assert counts.fatal_error is None, counts.fatal_error
    assert (await _user(sync_factory, ann_id)).hubspot_owner_id == "o-ann"
    assert (await _user(sync_factory, bob_id)).hubspot_owner_id == "o-bob"
    assert sorted(await _linked_audits(sync_factory)) == sorted([str(ann_id), str(bob_id)])


async def test_any_failure_of_the_link_step_leaves_the_deal_sync_running(sync_factory, monkeypatch):
    await _undecided_pair(sync_factory)

    async def broken(session):
        raise RuntimeError("the link step failed in some other way")

    monkeypatch.setattr(hubspot_backfill, "link_all_by_email", broken)
    counts = await run_backfill(_stub(), session_factory=sync_factory)
    assert counts.fatal_error is None, counts.fatal_error
    assert counts.scan_completed and counts.deals_written == 1


async def test_the_bulk_link_reports_a_database_error_as_nothing_linked(sync_factory, monkeypatch):
    ann_id, _ = await _undecided_pair(sync_factory)
    async with sync_factory() as s:
        s.add(HubspotOwner(id="o-ann", email="ann.a@example.test", first_name="Ann", last_name="A", archived=False))
        await s.commit()

    async def deadlocked(session, **kwargs):
        raise _deadlock()

    monkeypatch.setattr(hubspot_owners, "append_audit", deadlocked)
    async with sync_factory() as s:
        assert await link_all_by_email(s) == 0
        # The session's transaction is still usable.
        assert (await s.scalar(select(func.count()).select_from(User))) == 2
        await s.commit()
    assert (await _user(sync_factory, ann_id)).hubspot_owner_id is None


# --- the real races on PostgreSQL ---------------------------------------------------------------------------------


def _pg_async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@pytest_asyncio.fixture
async def pg_factory():
    if not _PG_URL:
        pytest.skip("requires postgres; set DEALGATE_POSTGRES_URL to run")
    engine = create_async_engine(_pg_async_url(_PG_URL))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()


@needs_postgres
async def test_postgres_sign_in_racing_another_link_of_the_same_owner(pg_factory):
    # Two DealGate rows whose emails differ only in case (intake keeps HubSpot's casing).
    tag = uuid.uuid4().hex[:8]
    intake_id, login_id = uuid.uuid4(), uuid.uuid4()
    async with pg_factory() as s:
        now = datetime.now(UTC)
        s.add_all([
            User(id=intake_id, email=f"Rita.Rep.{tag}@Example.test", name="Rita (intake row)", groups=[],
                 created_at=now - timedelta(days=30)),
            User(id=login_id, email=f"rita.rep.{tag}@example.test", name="Rita Rep", groups=["Sales"],
                 created_at=now - timedelta(days=1)),
            HubspotOwner(id=f"o-{tag}", email=f"rita.rep.{tag}@example.test", first_name="Rita", last_name="Rep",
                         archived=False),
        ])
        await s.commit()
    first, second = pg_factory(), pg_factory()
    try:
        # The first session links the owner to the intake row and has not committed yet.
        await first.execute(update(User).where(User.id == intake_id)
                            .values(hubspot_owner_id=f"o-{tag}", hubspot_owner_link="email"))

        async def sign_in():
            return await canonical_actor(second, AuthUser(login_id, f"rita.rep.{tag}@example.test", "Rita Rep",
                                                          ("Sales",)))

        task = asyncio.create_task(sign_in())
        await asyncio.sleep(1.0)  # the sign-in waits on the first session's unique-index entry
        await first.commit()
        who = await task  # was a MissingGreenlet 500
        assert who.id == login_id
        await second.commit()
    finally:
        await first.close()
        await second.close()
    async with pg_factory() as s:
        login = await s.get(User, login_id)
        assert (login.hubspot_owner_id, login.hubspot_owner_link) == (None, None)
        assert (await s.get(User, intake_id)).hubspot_owner_id == f"o-{tag}"


@needs_postgres
async def test_postgres_bulk_link_and_a_sign_in_deadlock_without_an_error(pg_factory):
    tag = uuid.uuid4().hex[:8]
    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    async with pg_factory() as s:
        now = datetime.now(UTC)
        s.add_all([
            User(id=a_id, email=f"a-{tag}@example.test", name="A", groups=[], created_at=now - timedelta(minutes=2)),
            User(id=b_id, email=f"b-{tag}@example.test", name="B", groups=[], created_at=now - timedelta(minutes=1)),
            HubspotOwner(id=f"oa-{tag}", email=f"a-{tag}@example.test", first_name="A", last_name="A",
                         archived=False),
            HubspotOwner(id=f"ob-{tag}", email=f"b-{tag}@example.test", first_name="B", last_name="B",
                         archived=False),
        ])
        await s.commit()
    sync_session, sign_in_session = pg_factory(), pg_factory()
    try:
        # The sign-in has flushed B's last_login (it holds B's row lock), as ensure_user does first.
        b = await sign_in_session.get(User, b_id)
        b.last_login = datetime.now(UTC)
        await sign_in_session.flush()

        async def owner_sync() -> int:
            linked = await link_all_by_email(sync_session)
            await sync_session.commit()
            return linked

        task = asyncio.create_task(owner_sync())
        await asyncio.sleep(1.0)  # the sync linked A (audit lock held) and waits for B's row
        linked_at_sign_in = await link_by_email(sign_in_session, b)  # wants the audit lock: deadlock
        assert b.email == f"b-{tag}@example.test"  # the row is readable whichever side lost
        await sign_in_session.commit()
        linked_by_sync = await task
    finally:
        await sync_session.close()
        await sign_in_session.close()
    # Neither side raised. Whoever won, B is linked to its owner exactly once.
    async with pg_factory() as s:
        b_row = await s.get(User, b_id)
        assert b_row.hubspot_owner_id == f"ob-{tag}"
        assert linked_at_sign_in or linked_by_sync == 2
