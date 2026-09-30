"""S20 W1 D2: HubSpot owner mirror.

Persists every HubSpot owner (active + archived) into a local table so
the deal sales-owner display always resolves — including for deals
whose owner has since been deactivated in the portal (T04, T31).

Contract (D2, contracts §2):
- Deal sales owner = HubSpot owner id resolved through this mirror.
- Client account owner = HubSpot company owner property (a separate
  concept; not derived from a deal).
- Local assignee = DealGate user for actions/tasks only.

The intake worker and the backfill worker both call
:func:`sync_owner_mirror` at the start of their run. The mirror is a
read-optimised cache; every column is nullable except the primary key so
partially-hydrated rows never fail to persist.

Model note: :class:`HubspotOwner` is declared here because
``api/app/models/*`` is Lead-owned; the model registers on
``Base.metadata`` at import time so SQLite tests + the running Postgres
schema (after the Lead applies migration W1-...-01) both see the table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import Boolean, DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.integrations.hubspot import HubSpotClient
from app.services.sync_status import touch_source

log = structlog.get_logger("hubspot_owners")


class HubspotOwner(Base):
    """Mirror row for one HubSpot owner (active OR archived).

    Keyed by HubSpot ``owner id`` (the CRM v3 ``/crm/v3/owners`` id — NOT
    the user id and NOT a DealGate user UUID; that mapping is a separate
    join through :class:`~app.models.user.User.hubspot_owner_id` when we
    care about local login).
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
        return OwnerMirrorCounts(errors=1)
    try:
        archived_rows = await _iter_owners(client, archived=True)
    except Exception:
        # Archive fetch is best-effort; if HubSpot rejects the flag for
        # this portal we still get the active mirror correct.
        log.exception("hubspot_owner_mirror_archived_fetch_failed")
        archived_rows = []

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
