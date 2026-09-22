"""Signatories picker — backend surface (S12).

Three endpoints that feed the `SignatoriesPicker` component wired into both
the NeedsYouSection and the ScopeSection on the confirm screen:

- ``GET  /signatories/internal``           — authorized internal signatories
                                              from People & access (users in
                                              a governance group).
- ``GET  /clients/{client_id}/contacts``   — client-side signatories.
- ``POST /clients/{client_id}/contacts``   — inline "add contact"; idempotent
                                              on (client_id, email).

Persisting the picked signatories back onto the SOW happens through the
existing ``PATCH /sow/versions/{sow_version_id}/fields/signatories`` route —
one write path per confirm-screen field, per docs/directives/sow-first.md.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser, require_role
from app.db import get_session
from app.models.client import Client
from app.models.client_contact import ClientContact
from app.models.user import User
from app.services.user_provisioning import ensure_user
from app.services.user_identity import display_user_email, display_user_name


router = APIRouter(tags=["signatories"])


# --- schemas ---------------------------------------------------------------


class InternalSignatoryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    groups: list[str] = Field(default_factory=list)


class ClientContactRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    email: str
    title: str | None = None


class ClientContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    title: str | None = Field(default=None, max_length=255)


# The picker is read by every governance role and writable by anyone who
# can move a SOW forward. Kept the same set as the staffing endpoints.
_PICK_ROLES: tuple[str, ...] = (
    "Sales",
    "SalesLeader",
    "Delivery",
    "Finance",
    "Legal",
    "HR",
    "CEO",
    "SystemAdmin",
)

# Groups whose members show up as "internal signatories". Anyone in one of
# these can sign on SmarTek21's side of a SOW. See docs/directives/gm-correctness.md §4.
_INTERNAL_SIGNATORY_GROUPS: frozenset[str] = frozenset(
    {
        "CEO",
        "SalesLeader",
        "Finance",
        "Legal",
        "SystemAdmin",
        "Delivery",
    }
)


# --- endpoints -------------------------------------------------------------


@router.get("/signatories/internal", response_model=list[InternalSignatoryRow])
async def list_internal_signatories(
    _user: AuthUser = Depends(require_role(*_PICK_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> list[InternalSignatoryRow]:
    """Authorised internal signatories — the "People & access" side of the picker."""

    rows = (
        (await session.execute(select(User).order_by(User.name)))
        .scalars()
        .all()
    )
    out: list[InternalSignatoryRow] = []
    for u in rows:
        groups = list(u.groups or [])
        if not any(g in _INTERNAL_SIGNATORY_GROUPS for g in groups):
            continue
        out.append(
            InternalSignatoryRow(
                id=u.id,
                name=display_user_name(u.name, u.email),
                email=display_user_email(u.email),
                groups=groups,
            )
        )
    return out


@router.get(
    "/clients/{client_id}/contacts",
    response_model=list[ClientContactRow],
)
async def list_client_contacts(
    client_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*_PICK_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> list[ClientContactRow]:
    """Client-side signatories previously entered for this client."""

    exists = await session.get(Client, client_id)
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="client not found"
        )
    rows = (
        (
            await session.execute(
                select(ClientContact)
                .where(ClientContact.client_id == client_id)
                .order_by(ClientContact.name)
            )
        )
        .scalars()
        .all()
    )
    return [ClientContactRow.model_validate(r) for r in rows]


@router.post(
    "/clients/{client_id}/contacts",
    response_model=ClientContactRow,
    status_code=status.HTTP_201_CREATED,
)
async def create_client_contact(
    client_id: uuid.UUID,
    body: ClientContactCreate,
    user: AuthUser = Depends(require_role(*_PICK_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> ClientContactRow:
    """Inline "add contact" from the picker. Idempotent on (client_id, email)."""

    if (await session.get(Client, client_id)) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="client not found"
        )

    # Idempotency: if the same email already exists for this client, return it
    # instead of raising a 409 — the picker's inline add is a "make sure this
    # contact exists" call, not "create only".
    existing = (
        await session.execute(
            select(ClientContact).where(
                ClientContact.client_id == client_id,
                ClientContact.email == str(body.email),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return ClientContactRow.model_validate(existing)

    db_user = await ensure_user(session, user)
    row = ClientContact(
        id=uuid.uuid4(),
        client_id=client_id,
        name=body.name.strip(),
        email=str(body.email),
        title=(body.title.strip() if body.title else None),
        created_by=db_user.id,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        # Race: another writer inserted the same (client_id, email) between
        # the SELECT and the INSERT. Return the persisted row.
        await session.rollback()
        winner = (
            await session.execute(
                select(ClientContact).where(
                    ClientContact.client_id == client_id,
                    ClientContact.email == str(body.email),
                )
            )
        ).scalar_one()
        return ClientContactRow.model_validate(winner)

    await append_audit(
        session,
        actor_id=db_user.id,
        action="client_contact.created",
        entity="client_contact",
        entity_id=str(row.id),
        before=None,
        after={
            "client_id": str(client_id),
            "name": row.name,
            "email": row.email,
            "title": row.title,
        },
    )
    await session.commit()
    return ClientContactRow.model_validate(row)
