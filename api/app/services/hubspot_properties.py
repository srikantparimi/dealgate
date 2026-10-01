"""S20 W1 D10: HubSpot custom-property discovery + type-aware mirroring.

The Business Unit field is a *custom* deal (or company) property in
HubSpot; its internal name, object type, option labels and even
existence differ per portal. This module discovers it programmatically
so the mirror doesn't hard-code a guess.

Behaviour (contracts §2 D10):

1. Walk ``/crm/v3/properties/deals`` first.
2. If not present, walk ``/crm/v3/properties/companies``.
3. Match on: ``type == "enumeration"`` AND the internal name OR label
   contains one of ``business_unit`` / ``business unit`` / ``bu``.
4. Record ``{internal_name, object_type, label, type, options[]}`` into
   :class:`HubspotPropertyMapping` under key ``business_unit``.
5. Not found → state ``blocked`` with the searched names as evidence.

The write path is idempotent — a re-run either updates the mapping in
place (option list changed) or leaves it alone (unchanged).

Read side: :func:`get_business_unit_mapping` returns the current
mapping (or ``None`` if unknown) so callers know:
- ``object_type`` (deal vs company) — determines which endpoint the
  mirror reads from.
- ``options`` — the id→label pairs to render on filter chips.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JsonB
from app.integrations.hubspot import HubSpotClient
from app.services.sync_status import touch_source

log = structlog.get_logger("hubspot_properties")


# Match patterns for the Business Unit property. Ordered from most
# specific to least; the first hit wins. ``re.IGNORECASE`` on match.
_BU_NAME_HINTS: tuple[str, ...] = (
    r"^business[_ ]unit$",
    r"^bu$",
    r"business[_ ]unit",
    r"\bbu\b",
)


class HubspotPropertyMapping(Base):
    """Discovered mapping for a custom HubSpot property (D10).

    One row per canonical DealGate key (``business_unit`` today; future
    slices may add ``industry``, ``deal_type``, etc). ``options`` is a
    JSONB array of ``{value, label, displayOrder, hidden}`` dicts
    verbatim from the HubSpot properties response, so a change in the
    upstream option list is one commit away.
    """

    __tablename__ = "hubspot_property_mapping"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    internal_name: Mapped[str] = mapped_column(String(128), nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "deal" | "company"
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "enumeration" | ...
    options: Mapped[Any | None] = mapped_column(JsonB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


@dataclass(frozen=True)
class DiscoveryResult:
    key: str
    found: bool
    internal_name: str | None
    object_type: str | None
    label: str | None
    field_type: str | None
    options: list[dict[str, Any]] | None
    evidence: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "found": self.found,
            "internal_name": self.internal_name,
            "object_type": self.object_type,
            "label": self.label,
            "field_type": self.field_type,
            "options": self.options,
            "evidence": self.evidence,
        }


def _matches(prop: dict[str, Any]) -> bool:
    """Return True iff ``prop`` looks like a Business Unit property."""

    ftype = (prop.get("type") or "").lower()
    if ftype != "enumeration":
        return False
    name = str(prop.get("name") or "")
    label = str(prop.get("label") or "")
    for pattern in _BU_NAME_HINTS:
        if re.search(pattern, name, flags=re.IGNORECASE):
            return True
        if re.search(pattern, label, flags=re.IGNORECASE):
            return True
    return False


def _extract_options(prop: dict[str, Any]) -> list[dict[str, Any]]:
    raw = prop.get("options") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for o in raw:
        if not isinstance(o, dict):
            continue
        out.append(
            {
                "value": o.get("value"),
                "label": o.get("label"),
                "display_order": o.get("displayOrder"),
                "hidden": bool(o.get("hidden", False)),
            }
        )
    return out


async def _list_properties(
    client: HubSpotClient, *, object_type: str
) -> list[dict[str, Any]]:
    """GET /crm/v3/properties/{object_type} — returns the properties array."""

    payload = await client._get(f"/crm/v3/properties/{object_type}")  # noqa: SLF001
    results = payload.get("results") or []
    return results if isinstance(results, list) else []


async def discover_business_unit(
    session: AsyncSession, client: HubSpotClient
) -> DiscoveryResult:
    """Walk deal → company properties looking for Business Unit.

    Persists the result via :func:`_upsert_mapping` and stamps
    ``hubspot_property_business_unit`` on ``sync_status``. Returns the
    :class:`DiscoveryResult` so the settings integration page can render
    the exact evidence (searched names, matched property, options).
    """

    # Guard the table's existence for the pre-migration window.
    try:
        await session.execute(select(HubspotPropertyMapping).limit(1))
    except Exception as exc:  # pragma: no cover - guarded staging path
        log.warning(
            "hubspot_property_mapping_table_missing",
            error_type=type(exc).__name__,
        )
        return DiscoveryResult(
            key="business_unit",
            found=False,
            internal_name=None,
            object_type=None,
            label=None,
            field_type=None,
            options=None,
            evidence={"error": "hubspot_property_mapping table not present"},
        )

    searched: dict[str, list[str]] = {"deal": [], "company": []}
    hit: dict[str, Any] | None = None
    hit_object: str | None = None
    for object_type in ("deals", "companies"):
        try:
            props = await _list_properties(client, object_type=object_type)
        except Exception:
            log.exception(
                "hubspot_properties_fetch_failed", object_type=object_type
            )
            continue
        canonical_object = "deal" if object_type == "deals" else "company"
        for p in props:
            searched[canonical_object].append(str(p.get("name") or ""))
            if _matches(p):
                hit = p
                hit_object = canonical_object
                break
        if hit is not None:
            break

    if hit is None:
        # Blocked with evidence — the caller (settings integration page)
        # renders the searched names so a human can tell whether the
        # portal is missing the property or we're looking for the wrong
        # thing.
        await touch_source(
            session,
            source="hubspot_property_business_unit",
            success=False,
            error="business_unit_not_found",
        )
        return DiscoveryResult(
            key="business_unit",
            found=False,
            internal_name=None,
            object_type=None,
            label=None,
            field_type=None,
            options=None,
            evidence={
                "searched_deal_property_names": searched["deal"],
                "searched_company_property_names": searched["company"],
                "hints_used": list(_BU_NAME_HINTS),
            },
        )

    options = _extract_options(hit)
    internal_name = str(hit.get("name") or "")
    label = str(hit.get("label") or internal_name)
    field_type = str(hit.get("type") or "enumeration")
    await _upsert_mapping(
        session,
        key="business_unit",
        internal_name=internal_name,
        object_type=hit_object or "deal",
        label=label,
        field_type=field_type,
        options=options,
    )
    await touch_source(
        session,
        source="hubspot_property_business_unit",
        success=True,
        error=None,
    )
    log.info(
        "hubspot_property_business_unit_discovered",
        internal_name=internal_name,
        object_type=hit_object,
        option_count=len(options),
    )
    return DiscoveryResult(
        key="business_unit",
        found=True,
        internal_name=internal_name,
        object_type=hit_object,
        label=label,
        field_type=field_type,
        options=options,
        evidence={
            "matched_property": {
                "name": internal_name,
                "label": label,
                "type": field_type,
            }
        },
    )


async def _upsert_mapping(
    session: AsyncSession,
    *,
    key: str,
    internal_name: str,
    object_type: str,
    label: str,
    field_type: str,
    options: list[dict[str, Any]],
) -> HubspotPropertyMapping:
    row = await session.get(HubspotPropertyMapping, key)
    if row is None:
        row = HubspotPropertyMapping(
            key=key,
            internal_name=internal_name,
            object_type=object_type,
            label=label,
            field_type=field_type,
            options=options,
        )
        session.add(row)
    else:
        row.internal_name = internal_name
        row.object_type = object_type
        row.label = label
        row.field_type = field_type
        row.options = options
    await session.flush()
    return row


async def get_business_unit_mapping(
    session: AsyncSession,
) -> HubspotPropertyMapping | None:
    """Return the current Business Unit mapping, or ``None`` when unknown.

    W2's filter bar reads this to render the BU multi-select; when it
    returns ``None`` the UI renders the ``blocked`` state instead.
    """

    try:
        return await session.get(HubspotPropertyMapping, "business_unit")
    except Exception:  # pragma: no cover - table-missing guard
        return None
