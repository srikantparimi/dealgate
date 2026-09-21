"""S13a-B4 — `ensure_user` hydrates missing email/name from Cognito.

The access token doesn't carry `email` / `name` claims; the auth layer
falls back to `sub` for both when they're absent, so a plain
`ensure_user` call would store the sub-UUID as both fields (that is why
the Pipeline page rendered "Owner: 112b05a0-…" before this fix).

This test pins the behaviour:

- When the token's email/name look like the sub, `ensure_user` calls the
  hydrate helper (mocked to return real values).
- Existing rows with `email`/`name == sub` are opportunistically backfilled
  on the next call.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.auth import AuthUser
from app.models.user import User
from app.services.user_provisioning import _looks_like_uuid, ensure_user


def test_looks_like_uuid_detects_bare_and_hyphenated():
    assert _looks_like_uuid("112b05a0-4061-7020-a17e-d557d60ac626")
    assert _looks_like_uuid(None)
    assert _looks_like_uuid("")
    assert not _looks_like_uuid("jane@example.com")
    assert not _looks_like_uuid("Jane Signer")


@pytest.mark.asyncio
async def test_ensure_user_hydrates_when_token_lacks_email_name(session):
    """Access token → email/name == sub → hydrate from Cognito."""

    sub = uuid.uuid4()
    actor = AuthUser(
        id=sub,
        email=str(sub),  # access token fallback
        name=str(sub),
        groups=("SystemAdmin",),
    )

    with patch(
        "app.services.user_provisioning.hydrate_from_cognito",
        return_value=("real@smartek21.com", "Real Person"),
    ) as m:
        row = await ensure_user(session, actor)
        assert m.call_count == 1
        assert m.call_args.args[0] == str(sub)

    assert row.email == "real@smartek21.com"
    assert row.name == "Real Person"


@pytest.mark.asyncio
async def test_ensure_user_backfills_existing_row(session):
    """A previously-provisioned row with `name == sub` heals on next call."""

    sub = uuid.uuid4()
    session.add(
        User(
            id=sub,
            email=str(sub),
            name=str(sub),
            groups=["SystemAdmin"],
        )
    )
    await session.commit()

    actor = AuthUser(
        id=sub, email=str(sub), name=str(sub), groups=("SystemAdmin",)
    )
    with patch(
        "app.services.user_provisioning.hydrate_from_cognito",
        return_value=("adopted@smartek21.com", "Adopted Name"),
    ):
        row = await ensure_user(session, actor)

    assert row.email == "adopted@smartek21.com"
    assert row.name == "Adopted Name"


@pytest.mark.asyncio
async def test_ensure_user_does_not_hydrate_when_token_has_email(session):
    """Real email present → no Cognito call (saves a round-trip)."""

    sub = uuid.uuid4()
    actor = AuthUser(
        id=sub,
        email="already@smartek21.com",
        name="Already Named",
        groups=("SystemAdmin",),
    )
    with patch(
        "app.services.user_provisioning.hydrate_from_cognito",
        return_value=(None, None),
    ) as m:
        row = await ensure_user(session, actor)
    assert m.call_count == 0
    assert row.email == "already@smartek21.com"
    assert row.name == "Already Named"


@pytest.mark.asyncio
async def test_ensure_user_survives_cognito_hydrate_failure(session):
    """Cognito outage → still creates the row (with sub-fallback fields)
    rather than 500-ing the caller."""

    sub = uuid.uuid4()
    actor = AuthUser(
        id=sub, email=str(sub), name=str(sub), groups=("SystemAdmin",)
    )
    with patch(
        "app.services.user_provisioning.hydrate_from_cognito",
        return_value=(None, None),
    ):
        row = await ensure_user(session, actor)
    assert row.id == sub
    # Still stored with the sub as email/name — the caller can hydrate
    # later; the important thing is the row exists so FK writes proceed.
    assert row.email == str(sub)
