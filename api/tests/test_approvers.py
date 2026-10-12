"""Approver resolver tests (Sprint 9 wave 1)."""

from __future__ import annotations

import uuid

import pytest

from app.models.approval_routing import ApprovalGroup
from app.models.user import User
from app.services.approvers import resolve, resolve_all, upsert_owner


async def _make_user(session, *, email: str, groups: list[str]) -> User:
    user = User(id=uuid.uuid4(), email=email, name=email.split("@")[0], groups=groups)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_resolve_prefers_owner_row_over_group(session):
    named = await _make_user(session, email="dev-lead@x.com", groups=["Delivery"])
    generic = await _make_user(session, email="dev-generic@x.com", groups=["Delivery"])
    await upsert_owner(
        session, function="delivery", business_unit="US", user_id=named.id
    )
    _ = generic  # unused; kept to prove the group_fallback candidate isn't picked

    result = await resolve(session, function="delivery", business_unit="US")
    assert result.user_id == named.id
    assert result.source in ("owner_row", "owner_row_default")


@pytest.mark.asyncio
async def test_resolve_prefers_configured_approval_group_default(session):
    configured = await _make_user(
        session, email="delivery-owner@x.com", groups=["Delivery"]
    )
    legacy = await _make_user(
        session, email="legacy-delivery@x.com", groups=["Delivery"]
    )
    await upsert_owner(
        session, function="delivery", business_unit=None, user_id=legacy.id
    )
    session.add(
        ApprovalGroup(
            function="delivery",
            member_ids=[str(configured.id)],
            backup_ids=[],
            default_approver_id=configured.id,
        )
    )
    await session.flush()

    result = await resolve(session, function="delivery")

    assert result.user_id == configured.id
    assert result.name == "delivery-owner"
    assert result.email == "delivery-owner@x.com"
    assert result.source == "approval_group_default"


@pytest.mark.asyncio
async def test_resolve_group_fallback_when_no_row(session):
    user = await _make_user(session, email="hr@x.com", groups=["HR"])
    result = await resolve(session, function="hr", business_unit="US")
    assert result.user_id == user.id
    assert result.source == "group_fallback"


@pytest.mark.asyncio
async def test_resolve_none_when_no_owner_no_group(session):
    result = await resolve(session, function="finance", business_unit="US")
    assert result.user_id is None
    assert result.source == "none"


@pytest.mark.asyncio
async def test_resolve_business_unit_null_fallback(session):
    generic = await _make_user(session, email="legal-any@x.com", groups=["Legal"])
    await upsert_owner(
        session, function="legal", business_unit=None, user_id=generic.id
    )
    # Ask for a specific BU — no exact match, so fall through to the
    # BU=NULL row before the group fallback.
    result = await resolve(session, function="legal", business_unit="EMEA")
    assert result.user_id == generic.id
    assert result.source in ("owner_row", "owner_row_default")


@pytest.mark.asyncio
async def test_resolve_all_returns_five_mandatory_functions(session):
    result = await resolve_all(session)
    assert set(result.keys()) == {"delivery", "hr", "sales", "finance", "legal"}


@pytest.mark.asyncio
async def test_resolve_invalid_function_raises(session):
    with pytest.raises(ValueError):
        await resolve(session, function="nonsense")


@pytest.mark.asyncio
async def test_upsert_is_idempotent(session):
    user = await _make_user(session, email="d@x.com", groups=["Delivery"])
    row1 = await upsert_owner(session, function="delivery", business_unit=None, user_id=user.id)
    row2 = await upsert_owner(session, function="delivery", business_unit=None, user_id=user.id)
    assert row1.id == row2.id
