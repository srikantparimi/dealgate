"""S12 — signatories picker backend.

Three endpoints; one write path (the existing `confirm_field` for the
`signatories` field). Tests cover:

- internal signatories list only returns users in a governance group;
- client contacts list is scoped to a client and 404s when the client
  does not exist;
- inline create is idempotent on (client_id, email) so the picker's
  "add contact" button never doubles a row.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import get_session
from app.main import app
from app.models.client import Client
from app.models.user import User


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


ADMIN = _uid("s12-picker-admin@smartek21.com")


@pytest_asyncio.fixture
async def http_admin(session, monkeypatch):
    """Anyone with SystemAdmin can drive the picker.

    Local-dev auth reads the user id from `X-Test-User` and the group
    list from `DEALGATE_TEST_GROUPS` (see `app/auth/dev.py`); the DB row
    is only used for `ensure_user`. `get_session` is overridden so the
    HTTP handler sees the same rows the fixture just committed.
    """

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    session.add(
        User(
            id=ADMIN,
            email="s12-picker-admin@smartek21.com",
            name="Picker Admin",
            groups=["SystemAdmin"],
        )
    )
    await session.commit()

    async def _override_session():
        yield session

    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)
    headers = {"X-Test-User": "s12-picker-admin@smartek21.com"}
    try:
        async with AsyncClient(
            transport=transport, base_url="http://testserver", headers=headers
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest_asyncio.fixture
async def client_row(session):
    row = Client(
        id=uuid.uuid4(),
        name="Peppermill Casino",
        hubspot_company_id=None,
    )
    session.add(row)
    await session.commit()
    return row


@pytest.mark.asyncio
async def test_internal_signatories_only_returns_governance_group_members(
    http_admin, session
):
    """Marketing / Presales / plain users don't show up as authorised signatories."""

    session.add(
        User(
            id=_uid("s12-marketing@smartek21.com"),
            email="s12-marketing@smartek21.com",
            name="Marketing Mia",
            groups=["Marketing"],
        )
    )
    session.add(
        User(
            id=_uid("s12-legal@smartek21.com"),
            email="s12-legal@smartek21.com",
            name="Legal Larry",
            groups=["Legal"],
        )
    )
    await session.commit()

    r = await http_admin.get("/signatories/internal")
    assert r.status_code == 200, r.text
    emails = {row["email"] for row in r.json()}
    assert "s12-legal@smartek21.com" in emails
    assert "s12-marketing@smartek21.com" not in emails


async def test_uuid_profile_names_never_leak_into_signatories_or_people(http_admin, session):
    placeholder = uuid.uuid4()
    session.add(User(id=placeholder, name=str(placeholder), email="jane.signer@example.com", groups=["Finance"]))
    await session.commit()
    signatories = (await http_admin.get("/signatories/internal")).json()
    people = (await http_admin.get("/admin/users")).json()["items"]
    for rows in (signatories, people):
        row = next(u for u in rows if u["id"] == str(placeholder))
        assert row["name"] == "jane.signer@example.com"


@pytest.mark.asyncio
async def test_client_contacts_404_on_missing_client(http_admin):
    r = await http_admin.get(f"/clients/{uuid.uuid4()}/contacts")
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_client_contacts_create_then_list(http_admin, client_row):
    body = {"name": "Jane Signer", "email": "jane@peppermill.example", "title": "CFO"}
    r = await http_admin.post(
        f"/clients/{client_row.id}/contacts", json=body
    )
    assert r.status_code == 201, r.text
    first = r.json()
    assert first["email"] == body["email"]
    assert first["title"] == "CFO"

    listed = await http_admin.get(f"/clients/{client_row.id}/contacts")
    assert listed.status_code == 200
    rows = listed.json()
    assert any(c["id"] == first["id"] for c in rows)


@pytest.mark.asyncio
async def test_client_contacts_create_is_idempotent_on_email(
    http_admin, client_row
):
    body = {"name": "Jane Signer", "email": "jane2@peppermill.example"}
    a = await http_admin.post(
        f"/clients/{client_row.id}/contacts", json=body
    )
    b = await http_admin.post(
        f"/clients/{client_row.id}/contacts", json=body
    )
    assert a.status_code == 201
    assert b.status_code == 201
    assert a.json()["id"] == b.json()["id"], "duplicate email should return the same row"


@pytest.mark.asyncio
async def test_client_contacts_email_scoped_by_client(
    http_admin, client_row, session
):
    """Same email, different clients → two rows."""

    other = Client(
        id=uuid.uuid4(),
        name="Other Client",
        hubspot_company_id=None,
    )
    session.add(other)
    await session.commit()

    body = {"name": "Same Person", "email": "sameemail@example.com"}
    a = await http_admin.post(
        f"/clients/{client_row.id}/contacts", json=body
    )
    b = await http_admin.post(
        f"/clients/{other.id}/contacts", json=body
    )
    assert a.status_code == 201
    assert b.status_code == 201
    assert a.json()["id"] != b.json()["id"]
