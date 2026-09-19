"""Client rate cards — per-client, MSA-sourced bill rates.

S9 wave 1. Split from the single ``rate_cards`` service per
``docs/sow-first-principles.md``. This module owns the **revenue** side
(bill rates by client legal entity). Cost bands stay in
``app.services.rate_cards`` (rename to ``cost_bands`` deferred so the
existing 635 tests keep passing during the split).

Resolution order for a SOW's revenue rates:

    client card  ->  SOW-stated override  ->  segment default  ->  company default

Every fallback returns a ``warning`` string so the caller can surface a
warning chip on the package (CLAUDE.md rule 10 — fallbacks are loud).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import append_audit
from app.models.client_rate_card import ClientRateCard, ClientRateCardRow

ALLOWED_LOCATIONS: frozenset[str] = frozenset({"US", "India"})
ALLOWED_UNITS: frozenset[str] = frozenset({"hourly", "daily", "monthly"})
ALLOWED_SOURCES: frozenset[str] = frozenset({"msa", "manual", "import"})

# Sanity floor for bill rates — a positive number under this triggers a
# warning but does not fail. Finance can confirm with an override.
SANITY_BILL_FLOOR: Decimal = Decimal("10.00")


@dataclass(frozen=True)
class ClientRateCardRowInput:
    role: str
    seniority: str
    location: str
    bill_rate: Decimal
    currency: str = "USD"
    unit: str = "hourly"
    effective_period: str | None = None


BillRateSource = Literal[
    "client_card", "sow_override", "segment_default", "company_default"
]


@dataclass(frozen=True)
class ResolvedBillRate:
    rate: Decimal | None
    source: BillRateSource
    warning: str | None
    card_id: uuid.UUID | None = None


# --- validation ------------------------------------------------------------


def _validate_row(row: ClientRateCardRowInput, idx: int) -> None:
    if not row.role.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"rows[{idx}].role is required",
        )
    if not row.seniority.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"rows[{idx}].seniority is required",
        )
    if row.location not in ALLOWED_LOCATIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"rows[{idx}].location must be one of {sorted(ALLOWED_LOCATIONS)}",
        )
    if row.unit not in ALLOWED_UNITS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"rows[{idx}].unit must be one of {sorted(ALLOWED_UNITS)}",
        )
    if row.bill_rate <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"rows[{idx}].bill_rate must be > 0",
        )
    if len(row.currency) != 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"rows[{idx}].currency must be a 3-letter code",
        )


# --- publish ---------------------------------------------------------------


async def publish_client_rate_card(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    client_id: uuid.UUID,
    rows: Sequence[ClientRateCardRowInput],
    effective_from: date,
    notes: str | None = None,
    source: str = "manual",
    source_document_id: uuid.UUID | None = None,
) -> ClientRateCard:
    """Create one immutable ``client_rate_card`` + its rows + audit.

    Raises 422 for validation failures. Empty ``rows`` is rejected — a
    card with no rates hides mistakes.
    """

    if source not in ALLOWED_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"source must be one of {sorted(ALLOWED_SOURCES)}",
        )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rows must not be empty",
        )
    for idx, row in enumerate(rows):
        _validate_row(row, idx)

    card = ClientRateCard(
        id=uuid.uuid4(),
        client_id=client_id,
        effective_from=effective_from,
        published_by=actor_id,
        notes=notes,
        source=source,
        source_document_id=source_document_id,
    )
    session.add(card)

    for row in rows:
        session.add(
            ClientRateCardRow(
                id=uuid.uuid4(),
                client_rate_card_id=card.id,
                role=row.role.strip(),
                seniority=row.seniority.strip(),
                location=row.location,
                bill_rate=row.bill_rate,
                currency=row.currency,
                unit=row.unit,
                effective_period=row.effective_period,
            )
        )
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action="client_rate_card.published",
        entity="client_rate_card",
        entity_id=str(card.id),
        before=None,
        after={
            "client_id": str(client_id),
            "effective_from": effective_from.isoformat(),
            "row_count": len(rows),
            "source": source,
            "source_document_id": (
                str(source_document_id) if source_document_id else None
            ),
            "notes": notes,
        },
    )
    await session.commit()

    return await _load_card_with_rows(session, card.id)


# --- read ------------------------------------------------------------------


async def _load_card_with_rows(
    session: AsyncSession, card_id: uuid.UUID
) -> ClientRateCard:
    stmt = (
        select(ClientRateCard)
        .options(selectinload(ClientRateCard.rows))
        .where(ClientRateCard.id == card_id)
    )
    return (await session.execute(stmt)).scalar_one()


async def active_client_rate_card(
    session: AsyncSession, client_id: uuid.UUID, at: date | None = None
) -> ClientRateCard | None:
    """Latest card for ``client_id`` with ``effective_from <= at`` (today)."""

    cutoff = at or date.today()
    stmt = (
        select(ClientRateCard)
        .options(selectinload(ClientRateCard.rows))
        .where(
            ClientRateCard.client_id == client_id,
            ClientRateCard.effective_from <= cutoff,
        )
        .order_by(
            ClientRateCard.effective_from.desc(),
            ClientRateCard.published_at.desc(),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# --- resolution ------------------------------------------------------------


def _row_matches(row: ClientRateCardRow, role: str, seniority: str, location: str) -> bool:
    return (
        row.role.strip().casefold() == role.strip().casefold()
        and row.seniority.strip().casefold() == seniority.strip().casefold()
        and row.location == location
    )


async def resolve_bill_rate(
    session: AsyncSession,
    *,
    client_id: uuid.UUID | None,
    role: str,
    seniority: str,
    location: str,
    sow_stated: Decimal | None = None,
    at: date | None = None,
) -> ResolvedBillRate:
    """Resolve the bill rate a GM calculation should use.

    Order per ``docs/sow-first-principles.md``:

    1. **SOW-stated override** — if the SOW explicitly names a bill rate
       for this line, that wins for revenue (the client card still
       records what the MSA said; the override is scoped to this SOW).
    2. **Client card** — the active card's matching row.
    3. **Segment default** — reserved for a later story; today we skip
       straight to (4) and emit a warning.
    4. **Company default** — ``None`` today (Finance has not published a
       company-wide bill rate table); emits a loud warning.

    Any fallback path returns a human-readable ``warning`` string so the
    caller can render a warning chip.
    """

    if location not in ALLOWED_LOCATIONS:
        raise ValueError(f"location must be one of {sorted(ALLOWED_LOCATIONS)}")

    if sow_stated is not None and sow_stated > 0:
        return ResolvedBillRate(
            rate=sow_stated,
            source="sow_override",
            warning=None,
            card_id=None,
        )

    if client_id is not None:
        card = await active_client_rate_card(session, client_id, at=at)
        if card is not None:
            for row in card.rows:
                if _row_matches(row, role, seniority, location):
                    return ResolvedBillRate(
                        rate=row.bill_rate,
                        source="client_card",
                        warning=None,
                        card_id=card.id,
                    )
            return ResolvedBillRate(
                rate=None,
                source="company_default",
                warning=(
                    f"no client-card row for {role}/{seniority}/{location} — "
                    "using company default (none configured)"
                ),
                card_id=card.id,
            )
        return ResolvedBillRate(
            rate=None,
            source="company_default",
            warning=(
                "client has no rate card — falling back to company default "
                "(none configured). Finance should publish a card."
            ),
            card_id=None,
        )

    return ResolvedBillRate(
        rate=None,
        source="company_default",
        warning="no client on this line — company default in use (none configured)",
        card_id=None,
    )


# --- serialisation ---------------------------------------------------------


def serialize_row(row: ClientRateCardRow) -> dict:
    return {
        "id": str(row.id),
        "role": row.role,
        "seniority": row.seniority,
        "location": row.location,
        "bill_rate": format(row.bill_rate, "f"),
        "currency": row.currency,
        "unit": row.unit,
        "effective_period": row.effective_period,
    }


def serialize_card(card: ClientRateCard, *, include_rows: bool = True) -> dict:
    payload: dict = {
        "id": str(card.id),
        "client_id": str(card.client_id),
        "effective_from": card.effective_from.isoformat(),
        "published_at": card.published_at.isoformat() if card.published_at else None,
        "published_by": str(card.published_by) if card.published_by else None,
        "notes": card.notes,
        "source": card.source,
        "source_document_id": (
            str(card.source_document_id) if card.source_document_id else None
        ),
        "row_count": len(card.rows),
    }
    if include_rows:
        payload["rows"] = [serialize_row(r) for r in card.rows]
    return payload


__all__ = [
    "ALLOWED_LOCATIONS",
    "ALLOWED_SOURCES",
    "ALLOWED_UNITS",
    "BillRateSource",
    "ClientRateCardRowInput",
    "ResolvedBillRate",
    "SANITY_BILL_FLOOR",
    "active_client_rate_card",
    "publish_client_rate_card",
    "resolve_bill_rate",
    "serialize_card",
    "serialize_row",
]
