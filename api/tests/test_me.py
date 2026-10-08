from __future__ import annotations

import uuid

import httpx
from sqlalchemy import select

from app.auth import AuthUser, current_user
from app.db import get_session
from app.main import app as main_app
from app.models.user import User
from app.services import user_provisioning


async def test_me_returns_canonical_invited_user_for_access_token(
    session, monkeypatch
):
    invited = User(
        id=uuid.uuid4(),
        email="owner@smartek21.com",
        name="Deal Owner",
        groups=["Sales"],
    )
    session.add(invited)
    await session.commit()

    cognito_sub = uuid.uuid4()
    raw_principal = AuthUser(
        id=cognito_sub,
        email=str(cognito_sub),
        name=str(cognito_sub),
        groups=["Sales"],
    )
    monkeypatch.setattr(
        user_provisioning,
        "hydrate_from_cognito",
        lambda _sub: (invited.email, invited.name),
    )

    async def _session_override():
        yield session

    main_app.dependency_overrides[current_user] = lambda: raw_principal
    main_app.dependency_overrides[get_session] = _session_override
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main_app), base_url="http://test"
        ) as client:
            response = await client.get("/me")
    finally:
        main_app.dependency_overrides.pop(current_user, None)
        main_app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json() == {
        "id": str(invited.id),
        "email": invited.email,
        "name": invited.name,
        "groups": ["Sales"],
    }
    users = (await session.execute(select(User))).scalars().all()
    assert [user.id for user in users] == [invited.id]
