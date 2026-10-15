"""S20 W1 D2: HubSpot owner mirror.

Persists every HubSpot owner (active + archived) into a local table so
the deal sales-owner display always resolves — including for deals
whose owner has since been deactivated in the portal (T04, T31).

Contract (D2, contracts §2):
- Deal sales owner = HubSpot owner id resolved through this mirror.
- Client account owner = HubSpot company owner property (a separate
  concept; not derived from a deal).
- Local assignee = DealGate user for actions/tasks only.

The backfill worker calls :func:`sync_owner_mirror` at the start of its
run and, once the mirror has committed, :func:`link_all_by_email` in a
transaction of its own (S23-PL2). The mirror is a read-optimised cache;
every column is nullable except the primary key so partially-hydrated rows
never fail to persist.

Model note: :class:`HubspotOwner` is declared here because
``api/app/models/*`` is Lead-owned; the model registers on
``Base.metadata`` at import time so SQLite tests + the running Postgres
schema (after the Lead applies migration W1-...-01) both see the table.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import Boolean, DateTime, String, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, aliased, mapped_column

from app.audit import append_audit
from app.db.base import Base
from app.integrations.hubspot import HubSpotClient
from app.models.user import User
from app.services.sync_status import touch_source
from app.services.user_identity import display_user_name, is_identity_placeholder

log = structlog.get_logger("hubspot_owners")


class HubspotOwner(Base):
    """Mirror row for one HubSpot owner (active OR archived).

    Keyed by HubSpot ``owner id`` (the CRM v3 ``/crm/v3/owners`` id — NOT
    the user id and NOT a DealGate user UUID). A DealGate user points at
    one of these rows through ``User.hubspot_owner_id`` (S23-PL2 B4, see
    :func:`link_by_email` and :func:`set_owner_link`).
    """

    __tablename__ = "hubspot_owner"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hubspot_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hubspot_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


@dataclass(frozen=True)
class OwnerMirrorCounts:
    active_seen: int = 0
    archived_seen: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "active_seen": self.active_seen,
            "archived_seen": self.archived_seen,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "errors": self.errors,
        }


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    s = str(raw)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.fromtimestamp(int(s) / 1000, tz=UTC)
    except (ValueError, OSError):
        return None


def _row_needs_update(row: HubspotOwner, payload: dict[str, Any]) -> bool:
    """Return True iff any field on the payload differs from the row."""

    def eq(a: Any, b: Any) -> bool:
        return (a or None) == (b or None)

    checks = [
        eq(row.user_id, payload.get("user_id")),
        eq(row.email, payload.get("email")),
        eq(row.first_name, payload.get("first_name")),
        eq(row.last_name, payload.get("last_name")),
        row.archived == bool(payload.get("archived")),
    ]
    return not all(checks)


def _apply(row: HubspotOwner, payload: dict[str, Any]) -> None:
    row.user_id = payload.get("user_id") or None
    row.email = payload.get("email") or None
    row.first_name = payload.get("first_name") or None
    row.last_name = payload.get("last_name") or None
    row.archived = bool(payload.get("archived"))
    row.hubspot_created_at = payload.get("hubspot_created_at")
    row.hubspot_updated_at = payload.get("hubspot_updated_at")


def _normalise_hubspot_row(entry: dict[str, Any], *, archived: bool) -> dict[str, Any]:
    return {
        "id": str(entry.get("id") or ""),
        "user_id": (str(entry.get("userId")) if entry.get("userId") is not None else None),
        "email": (entry.get("email") or "").strip() or None,
        "first_name": entry.get("firstName") or None,
        "last_name": entry.get("lastName") or None,
        "archived": archived,
        "hubspot_created_at": _parse_ts(entry.get("createdAt")),
        "hubspot_updated_at": _parse_ts(entry.get("updatedAt")),
    }


async def _iter_owners(
    client: HubSpotClient, *, archived: bool
) -> list[dict[str, Any]]:
    """Fetch every owner from the CRM v3 owners endpoint.

    HubSpot returns owners in pages of up to 500. We honour ``paging.next
    .after`` and stop when it is absent. ``archived`` is a query flag
    (per the HubSpot owners guide the archived listing is separate from
    the active listing — a single call cannot return both).
    """

    out: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        params: dict[str, Any] = {"archived": str(archived).lower(), "limit": 100}
        if after:
            params["after"] = after
        payload = await client._get("/crm/v3/owners", params=params)  # noqa: SLF001
        for entry in payload.get("results") or []:
            out.append(_normalise_hubspot_row(entry, archived=archived))
        after = ((payload.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    return out


async def sync_owner_mirror(
    session: AsyncSession, client: HubSpotClient
) -> OwnerMirrorCounts:
    """Refresh the owner mirror from the HubSpot CRM v3 owners endpoint.

    Called by the backfill (before deal upsert) and the intake worker
    (once per run so a freshly-added or newly-archived owner shows up on
    the next deal event without waiting for nightly reconcile).

    The write path is a plain UPSERT: existing rows are updated in place,
    new rows are inserted. Rows are never deleted — an owner archived
    upstream stays in the mirror with ``archived=True`` so historical
    deals still resolve their sales owner (D2 "include archived").

    D5 backward-compat: if the ``hubspot_owner`` table doesn't yet exist
    (Lead migration W1-...-01 not applied), the whole call is a no-op
    logging line and returns zero counts. Callers still work.
    """

    counts = OwnerMirrorCounts()

    # Guard: the table must exist. On SQLite (tests) create_all built it;
    # on Postgres it lands via the Lead's migration. Check once so a
    # pre-migration staging window doesn't fail every intake tick.
    try:
        await session.execute(select(HubspotOwner).limit(1))
    except Exception as exc:  # pragma: no cover - guarded staging path
        log.warning("hubspot_owner_mirror_table_missing", error_type=type(exc).__name__)
        return counts

    try:
        active_rows = await _iter_owners(client, archived=False)
    except Exception:
        log.exception("hubspot_owner_mirror_active_fetch_failed")
        await touch_source(session, source="hubspot_owner_mirror", success=False, error="active_owner_fetch_failed")
        return OwnerMirrorCounts(errors=1)
    try:
        archived_rows = await _iter_owners(client, archived=True)
    except Exception:
        log.exception("hubspot_owner_mirror_archived_fetch_failed")
        await touch_source(session, source="hubspot_owner_mirror", success=False, error="archived_owner_fetch_failed")
        return OwnerMirrorCounts(errors=1)

    counts = OwnerMirrorCounts(
        active_seen=len(active_rows),
        archived_seen=len(archived_rows),
    )

    inserted = 0
    updated = 0
    unchanged = 0
    for payload in active_rows + archived_rows:
        oid = payload["id"]
        if not oid:
            continue
        row = await session.get(HubspotOwner, oid)
        if row is None:
            row = HubspotOwner(id=oid)
            _apply(row, payload)
            session.add(row)
            inserted += 1
        elif _row_needs_update(row, payload):
            _apply(row, payload)
            updated += 1
        else:
            unchanged += 1

    counts = OwnerMirrorCounts(
        active_seen=len(active_rows),
        archived_seen=len(archived_rows),
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
    )

    await touch_source(
        session,
        source="hubspot_owner_mirror",
        success=True,
        error=None,
    )
    await session.flush()
    log.info("hubspot_owner_mirror_synced", **counts.as_dict())
    return counts


async def resolve_owner_by_id(
    session: AsyncSession, hubspot_owner_id: str
) -> HubspotOwner | None:
    """Read-side lookup: return the mirror row for a HubSpot owner id.

    W2's deal / client display calls this to convert a raw owner id into
    a name — including archived owners. The two "Unassigned" vs "Owner
    details unavailable" distinctions (D2) are decided by the caller:
    a NULL ``hubspot_owner_id`` on the deal → "Unassigned"; a non-null
    id that doesn't resolve here → "Owner details unavailable".
    """

    return await session.get(HubspotOwner, hubspot_owner_id)


# D2 display labels, exported so W2 / W4 / matrix asserts all share
# the same wording without importing tests.
OWNER_LABEL_UNASSIGNED = "Unassigned"
OWNER_LABEL_UNRESOLVED = "Owner details unavailable"


async def owner_display_label(
    session: AsyncSession, hubspot_owner_id: str | None
) -> str:
    """D2 wording helper.

    ``None`` (source is genuinely empty) → ``"Unassigned"``.
    Non-null id that misses the mirror → ``"Owner details unavailable"``.
    A resolved row prefers ``first + last``; falls back to ``email``,
    then to ``"Owner details unavailable"`` (the record exists but has
    no useful display name — treat it as an unresolved reference).

    Archived owners resolve to their name too (D2 spec: "include archived
    owners"), so a deal owned by a departed rep still renders the human's
    name rather than the id.
    """

    if hubspot_owner_id is None or not str(hubspot_owner_id).strip():
        return OWNER_LABEL_UNASSIGNED
    row = await resolve_owner_by_id(session, str(hubspot_owner_id))
    if row is None:
        return OWNER_LABEL_UNRESOLVED
    first = (row.first_name or "").strip()
    last = (row.last_name or "").strip()
    if first or last:
        return " ".join(x for x in (first, last) if x)
    if row.email:
        return row.email
    return OWNER_LABEL_UNRESOLVED


# --- S23-PL2 B4: DealGate user <-> HubSpot owner ---------------------------
#
# ``user.hubspot_owner_link`` records how the link was decided: ``email``
# (automatic) or ``admin`` (override; with no owner id it means an admin chose
# "no owner"). NULL means undecided, and only undecided users are linked
# automatically, so an admin's decision is never undone by a sync or a login.

OWNER_LINK_EMAIL = "email"
OWNER_LINK_ADMIN = "admin"


def owner_display_name(owner: HubspotOwner) -> str | None:
    """First and last name, else the email; None when the owner has neither."""

    first = (owner.first_name or "").strip()
    last = (owner.last_name or "").strip()
    if first or last:
        return " ".join(x for x in (first, last) if x)
    return (owner.email or "").strip() or None


def _link_values(user: User) -> dict[str, str | None]:
    return {"hubspot_owner_id": user.hubspot_owner_id, "hubspot_owner_link": user.hubspot_owner_link}


async def _apply_email_link(
    session: AsyncSession, user: User, owner_id: str, *, actor_id: uuid.UUID | None, trigger: str
) -> None:
    before = _link_values(user)
    user.hubspot_owner_id = owner_id
    user.hubspot_owner_link = OWNER_LINK_EMAIL
    user.hubspot_owner_linked_at = datetime.now(UTC)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="user.hubspot_owner_linked",
        entity="user",
        entity_id=str(user.id),
        before=before,
        after={**_link_values(user), "source": "email", "trigger": trigger},
    )


def _undecided(user: User) -> bool:
    return user.hubspot_owner_link is None and user.hubspot_owner_id is None


async def link_by_email(session: AsyncSession, user: User) -> bool:
    """Link ``user`` to the HubSpot owner that has their email, at sign-in.

    Exact email equality ignoring case (HubSpot and Cognito casing differ),
    active owners only. Nothing happens when the user is already decided, when
    two active owners share the address, or when the one owner is already
    another user's. Returns True when a link was written.
    """

    email = (user.email or "").strip()
    if not _undecided(user) or is_identity_placeholder(email) or "@" not in email:
        return False
    claimed_by = aliased(User)
    rows = (
        await session.execute(
            select(HubspotOwner.id, claimed_by.id)
            .outerjoin(claimed_by, claimed_by.hubspot_owner_id == HubspotOwner.id)
            .where(
                HubspotOwner.archived.is_(False),
                func.lower(HubspotOwner.email) == func.lower(email),
            )
        )
    ).all()
    if len(rows) != 1 or rows[0][1] is not None:
        return False
    user_id = user.id
    try:
        async with session.begin_nested():
            await _apply_email_link(session, user, rows[0][0], actor_id=user_id, trigger="sign_in")
    except DBAPIError as error:
        # Another session linked this owner to someone else at the same moment (the
        # unique index), or the owner sync's bulk link, holding the audit lock, waits
        # for this user's row (deadlock). Sign in unlinked; the next sign-in or owner
        # sync retries. The savepoint rollback expired the row: load it again before
        # anything reads it (a lazy load in async context is a 500).
        await session.refresh(user)
        log.warning("hubspot_owner_link_conflict" if isinstance(error, IntegrityError)
                    else "hubspot_owner_link_failed", user_id=str(user_id), error_type=type(error).__name__)
        return False
    return True


async def link_all_by_email(session: AsyncSession) -> int:
    """Bulk :func:`link_by_email` for every undecided user (owner sync).

    The backfill runs it after the owner mirror has committed, in a transaction
    of its own, and everything here happens inside one SAVEPOINT. It never
    raises a database error: a conflict with a sign-in or an admin, or a
    deadlock with a sign-in (this holds the audit lock while it waits for a
    user row the sign-in holds), is logged, nothing is linked this run, and the
    next run retries. The deal sync never depends on it.
    """

    planned = 0
    try:
        async with session.begin_nested():
            plan = await _email_link_plan(session)
            planned = len(plan)
            for user, owner_id in plan:
                await _apply_email_link(session, user, owner_id, actor_id=None, trigger="owner_sync")
    except DBAPIError as error:
        log.warning("hubspot_owner_bulk_link_conflict" if isinstance(error, IntegrityError)
                    else "hubspot_owner_bulk_link_failed", planned=planned, error_type=type(error).__name__)
        return 0
    if planned:
        log.info("hubspot_owner_bulk_linked", users_linked=planned)
    return planned


async def _email_link_plan(session: AsyncSession) -> list[tuple[User, str]]:
    """Each undecided user with exactly one active, unclaimed owner of the same email (oldest user first)."""

    users = (
        await session.execute(
            select(User, func.lower(User.email))
            .where(User.hubspot_owner_link.is_(None), User.hubspot_owner_id.is_(None))
            .order_by(User.created_at, User.id)
        )
    ).all()
    if not users:
        return []
    owners = (
        await session.execute(
            select(HubspotOwner.id, func.lower(HubspotOwner.email)).where(
                HubspotOwner.archived.is_(False), HubspotOwner.email.is_not(None)
            )
        )
    ).all()
    by_email: dict[str, list[str]] = {}
    for owner_id, email in owners:
        by_email.setdefault(email, []).append(owner_id)
    claimed = set(
        (await session.scalars(select(User.hubspot_owner_id).where(User.hubspot_owner_id.is_not(None)))).all()
    )
    plan: list[tuple[User, str]] = []
    for user, email in users:
        candidates = by_email.get(email or "", [])
        if is_identity_placeholder(user.email) or len(candidates) != 1 or candidates[0] in claimed:
            continue
        claimed.add(candidates[0])
        plan.append((user, candidates[0]))
    return plan


@dataclass(frozen=True)
class OwnerLink:
    """How a user's link reads on the admin users list."""

    name: str | None
    state: str  # active | archived | none


async def owner_links(session: AsyncSession, users: list[User]) -> dict[uuid.UUID, OwnerLink]:
    """The linked owner's display name and state for each user, in one statement.

    No owner → ``none``; an owner the mirror lists as archived, or one it no
    longer holds, → ``archived`` (shown as "Former HubSpot user").
    """

    ids = {u.hubspot_owner_id for u in users if u.hubspot_owner_id}
    owners = (
        {o.id: o for o in (await session.scalars(select(HubspotOwner).where(HubspotOwner.id.in_(ids)))).all()}
        if ids
        else {}
    )
    out: dict[uuid.UUID, OwnerLink] = {}
    for user in users:
        if not user.hubspot_owner_id:
            out[user.id] = OwnerLink(name=None, state="none")
            continue
        owner = owners.get(user.hubspot_owner_id)
        if owner is None:
            out[user.id] = OwnerLink(name=None, state="archived")
        else:
            out[user.id] = OwnerLink(name=owner_display_name(owner), state="archived" if owner.archived else "active")
    return out


async def list_owner_options(session: AsyncSession) -> list[dict[str, Any]]:
    """Every mirrored owner for the admin's link picker: active first, then former, each by name."""

    rows = (
        await session.execute(
            select(HubspotOwner, User.id, User.name, User.email).outerjoin(
                User, User.hubspot_owner_id == HubspotOwner.id
            )
        )
    ).all()
    options = [
        {
            "id": owner.id,
            "name": owner_display_name(owner),
            "email": owner.email,
            "archived": bool(owner.archived),
            "linked_user_id": str(user_id) if user_id else None,
            "linked_user_name": display_user_name(user_name, user_email) if user_id else None,
        }
        for owner, user_id, user_name, user_email in rows
    ]
    options.sort(key=lambda o: (o["archived"], (o["name"] or "").casefold(), o["id"]))
    return options


async def set_owner_link(
    session: AsyncSession, *, actor_id: uuid.UUID, user_id: uuid.UUID, hubspot_owner_id: str | None
) -> User:
    """Admin override: link ``user_id`` to an owner, or to no owner (``None``).

    The decision is recorded as ``admin`` so the automatic link never replaces
    it. 404 unknown user; 422 owner not in the mirror; 409 owner already
    linked to someone else (the message names that person).
    """

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    owner_id = hubspot_owner_id.strip() if hubspot_owner_id is not None else None
    if owner_id == "":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choose a HubSpot owner, or send null to unlink.",
        )
    if owner_id is not None:
        if await session.get(HubspotOwner, owner_id) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="That HubSpot owner is not in the owner list. Run the HubSpot sync, then try again.",
            )
        holder = (
            await session.scalars(select(User).where(User.hubspot_owner_id == owner_id, User.id != user.id))
        ).first()
        if holder is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{display_user_name(holder.name, holder.email)} is already linked to this HubSpot owner. "
                    "Unlink them first."
                ),
            )
    before = _link_values(user)
    if before == {"hubspot_owner_id": owner_id, "hubspot_owner_link": OWNER_LINK_ADMIN}:
        return user
    user.hubspot_owner_id = owner_id
    user.hubspot_owner_link = OWNER_LINK_ADMIN
    user.hubspot_owner_linked_at = datetime.now(UTC)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="user.hubspot_owner_overridden",
        entity="user",
        entity_id=str(user.id),
        before=before,
        after=_link_values(user),
    )
    return user
