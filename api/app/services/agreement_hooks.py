"""S24-AG1 B8 — a new client's default relationship (existing or net new).

One function, :func:`stamp_new_client`, is called from every path that creates a
client (HubSpot sync and its "Unknown company" placeholder, ``POST /clients``
and the forecast-model and workbook imports, SOW studio "create new", bulk SOW
import, legacy import, test fixtures). It never changes a client that already
has a relationship, and it applies the ONE rule in
:func:`app.services.agreement_status.relationship_of` (the contract's
``components.Cutover``):

* before the cutover nothing is stamped: the relationship is computed live and
  shown as provisional (agreement_status);
* after it, a client starts ``net_new`` unless its HubSpot company already has a
  Closed Won deal dated on or before the cutover (then ``existing``, basis
  ``closed_won``).

A client created from a HubSpot company has no deal linked at the moment its row
is created (the sync links the deal right after), so the rule cannot be judged
then. Such a client stays unstamped until :func:`settle_pending_relationships`
runs after a successful sync (``hubspot_sync_runs``), when every deal of the
company has been read; until then agreement_status judges it by the same rule,
so the page is right in between. Every other path has no HubSpot company and is
stamped at creation, inside the creating transaction.

A stamp writes one ``client.relationship_stamped`` audit row. HubSpot paths run
with no user and credit nobody (no system user is invented); the others credit
the person who created the client.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models.agreements import AgreementsSettings
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.services import agreement_audit
from app.services.agreement_status import ClientInput, DealInput, relationship_of

log = structlog.get_logger("agreement_hooks")

SETTLE_CHUNK = 25
SETTLE_ORIGIN = "hubspot_sync"


async def load_cutover(session: AsyncSession) -> tuple[date | None, datetime | None]:
    """(cutover date, when it was set). (None, None) before the first real batch or with no settings row
    (SQLite ``create_all`` has none; migration 0072 inserts it)."""
    row = (await session.execute(
        select(AgreementsSettings.cutover_date, AgreementsSettings.set_at).where(AgreementsSettings.id == 1)
    )).first()
    if row is None:
        return None, None
    return row[0], row[1]


def _deal_input(is_closed_won: bool, is_closed_lost: bool, close_date: date | None) -> DealInput:
    status = "won" if is_closed_won else "lost" if is_closed_lost else "open"
    return DealInput(status=status, close_date=close_date)


def _apply(client: Client, relationship: str, basis: str, actor_id: uuid.UUID | None, at: datetime) -> None:
    client.relationship = relationship
    client.relationship_basis = basis
    client.relationship_set_by = actor_id
    client.relationship_set_at = at


def _stamp_payload(client: Client, *, origin: str, cutover: date) -> dict[str, Any]:
    return {
        "client_id": str(client.id), "client_name": client.name,
        "relationship": client.relationship, "basis": client.relationship_basis,
        "origin": origin, "cutover": cutover.isoformat(),
    }


async def _audit_stamp(session: AsyncSession, client: Client, *, actor_id: uuid.UUID | None, origin: str,
                       cutover: date, correlation_id: str | None) -> None:
    await append_audit(
        session, actor_id=actor_id, action=agreement_audit.RELATIONSHIP_STAMPED, entity="client",
        entity_id=str(client.id), before={"relationship": None},
        after=_stamp_payload(client, origin=origin, cutover=cutover), correlation_id=correlation_id,
    )


async def stamp_new_client(
    session: AsyncSession,
    client: Client,
    *,
    actor_id: uuid.UUID | None,
    origin: str,
    correlation_id: str | None = None,
) -> str | None:
    """Stamp a client just created, in the caller's transaction (the caller commits).

    Returns the relationship stamped, the one it already had, or None when nothing is stamped (before the
    cutover, or a HubSpot company client whose deals are not linked yet).
    """
    if client.relationship is not None:
        return client.relationship  # never moved by the rule
    if client.hubspot_company_id:
        # Its deals are linked after this row exists; settle_pending_relationships judges it after the sync.
        return None
    cutover, _set_at = await load_cutover(session)
    if cutover is None:
        return None
    # No HubSpot company, so no Closed Won deal can count: the rule gives net_new / none.
    relationship, basis, _provisional = relationship_of(ClientInput(id=client.id, name=client.name or ""), cutover)
    _apply(client, relationship, basis, actor_id, datetime.now(UTC))
    await session.flush()
    await _audit_stamp(session, client, actor_id=actor_id, origin=origin, cutover=cutover,
                       correlation_id=correlation_id)
    log.info("agreements_relationship_stamped", client_id=str(client.id), relationship=relationship,
             origin=origin)
    return relationship


async def settle_pending_relationships(
    session: AsyncSession,
    *,
    client_ids: list[uuid.UUID] | None = None,
    origin: str = SETTLE_ORIGIN,
    correlation_id: str | None = None,
) -> int:
    """Stamp every client created since the cutover that is still unstamped, by the creation rule.

    Run after a successful HubSpot sync (every deal of every company has been read, so "no Closed Won deal
    dated on or before the cutover" is now a fact). Clients created before the cutover was set are left to
    the batch that set it. Commits every :data:`SETTLE_CHUNK` clients; each chunk locks its client rows
    first, re-checks that they are still unstamped (a writer's manual change always wins), stamps them and
    writes the audit rows last. Returns how many clients were stamped.
    """
    cutover, set_at = await load_cutover(session)
    if cutover is None:
        return 0
    pending = select(Client.id).where(Client.relationship.is_(None))
    if set_at is not None:
        pending = pending.where(Client.created_at >= set_at)
    if client_ids is not None:
        if not client_ids:
            return 0
        pending = pending.where(Client.id.in_(list(client_ids)))
    ids = sorted((await session.execute(pending)).scalars().all(), key=str)
    # Release the read transaction before locking (a chunk is its own transaction).
    await session.commit()
    stamped = 0
    for start in range(0, len(ids), SETTLE_CHUNK):
        chunk = ids[start:start + SETTLE_CHUNK]
        clients = list((await session.execute(
            select(Client).where(Client.id.in_(chunk), Client.relationship.is_(None))
            .order_by(Client.id).with_for_update().execution_options(populate_existing=True)
        )).scalars().all())
        if not clients:
            await session.commit()
            continue
        deals: dict[uuid.UUID, list[DealInput]] = defaultdict(list)
        for client_id, won, lost, close_date in (await session.execute(
            select(Opportunity.client_id, Opportunity.is_closed_won, Opportunity.is_closed_lost,
                   Opportunity.close_date)
            .where(Opportunity.client_id.in_([c.id for c in clients]), Opportunity.source == "hubspot",
                   Opportunity.archived_at.is_(None))
        )).all():
            deals[client_id].append(_deal_input(bool(won), bool(lost), close_date))
        now = datetime.now(UTC)
        for client in clients:
            facts = ClientInput(id=client.id, name=client.name or "", hubspot_company_id=client.hubspot_company_id,
                                deals=tuple(deals.get(client.id, ())))
            relationship, basis, _provisional = relationship_of(facts, cutover)
            _apply(client, relationship, basis, None, now)
        await session.flush()
        for client in clients:  # audit last, then commit
            await _audit_stamp(session, client, actor_id=None, origin=origin, cutover=cutover,
                               correlation_id=correlation_id)
        await session.commit()
        stamped += len(clients)
    if stamped:
        log.info("agreements_relationships_settled", stamped=stamped, cutover=cutover.isoformat())
    return stamped


__all__ = ["SETTLE_CHUNK", "load_cutover", "settle_pending_relationships", "stamp_new_client"]
