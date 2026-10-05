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
5. Persist explicit availability and searched names as evidence. Failed
   requests never establish absence, and multiple candidates never auto-bind.

The write path versions changed metadata, keeps unchanged metadata versions
stable, and retains last-good evidence when the provider becomes unavailable.

Read side: :func:`get_business_unit_mapping` returns the current
usable mapping (or ``None`` if not configured) so callers know:
- ``object_type`` (deal vs company) — determines which endpoint the
  mirror reads from.
- ``options`` — the id→label pairs to render on filter chips.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit import append_audit
from app.db.base import Base, JsonB
from app.integrations.hubspot import HubSpotClient
from app.services.sync_status import touch_source

log = structlog.get_logger("hubspot_properties")


# Match patterns for the Business Unit property. Ordered from most
# specific to least; all candidates are considered. ``re.IGNORECASE`` on match.
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
    __table_args__ = (
        CheckConstraint("mapping_version > 0", name="ck_hubspot_mapping_version"),
        CheckConstraint("availability_state IN ('unknown','configured','absent','ambiguous','unavailable')",
            name="ck_hubspot_mapping_availability"),
    )

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    internal_name: Mapped[str | None] = mapped_column(String(128))
    object_type: Mapped[str | None] = mapped_column(String(32))  # "deal" | "company"
    label: Mapped[str | None] = mapped_column(String(255))
    field_type: Mapped[str | None] = mapped_column(String(32))  # "enumeration" | ...
    options: Mapped[Any | None] = mapped_column(JsonB, nullable=True)
    availability_state: Mapped[str] = mapped_column(String(16), default="unknown", server_default="unknown")
    availability_reason: Mapped[str | None] = mapped_column(String(1024))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mapping_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    evidence: Mapped[Any | None] = mapped_column(JsonB)
    selected_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("user.id"))
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
    availability_state: str = "unknown"
    availability_reason: str | None = None
    mapping_version: int = 1

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
            "availability_state": self.availability_state,
            "availability_reason": self.availability_reason,
            "mapping_version": self.mapping_version,
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
    raw = prop.get("options")
    if not isinstance(raw, list):
        raise ValueError("invalid_options")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for option in raw:
        if not isinstance(option, dict):
            raise ValueError("invalid_option")
        value, label = option.get("value"), option.get("label")
        order, hidden = option.get("displayOrder"), option.get("hidden", False)
        if (not isinstance(value, str) or not value or value in seen
                or not isinstance(label, str) or not label
                or type(hidden) is not bool
                or (order is not None and type(order) is not int)):
            raise ValueError("invalid_option")
        seen.add(value)
        out.append({"value": value, "label": label,
                    "display_order": order, "hidden": hidden})
    return sorted(out, key=lambda option: option["value"])


async def _list_properties(client: HubSpotClient, *, object_type: str) -> list[dict[str, Any]]:
    payload = await client._get(f"/crm/v3/properties/{object_type}")  # noqa: SLF001
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("invalid_properties_response")
    props = payload["results"]
    seen: set[str] = set()
    for prop in props:
        if not isinstance(prop, dict):
            raise ValueError("invalid_property")
        if any(not isinstance(prop.get(key), str) or not prop[key]
               for key in ("name", "label", "type")):
            raise ValueError("invalid_property")
        if prop["name"] in seen:
            raise ValueError("duplicate_property")
        seen.add(prop["name"])
    return props


def _audit_snapshot(row: HubspotPropertyMapping) -> dict[str, Any]:
    return {
        "availability_state": row.availability_state or "unknown",
        "availability_reason": row.availability_reason,
        "mapping_version": row.mapping_version or 1,
        "internal_name": row.internal_name, "object_type": row.object_type,
        "label": row.label, "field_type": row.field_type, "options": row.options,
        "source": "hubspot_property_discovery",
    }


async def discover_business_unit(session: AsyncSession, client: HubSpotClient) -> DiscoveryResult:
    """Refresh a bound identity, or discover uniquely using deal-first precedence.

    Provider failures are availability observations, never proof of absence.
    Database failures propagate so callers cannot commit a fictitious discovery.
    The caller owns the transaction, including sync-status persistence.
    """
    row = await session.scalar(
        select(HubspotPropertyMapping)
        .where(HubspotPropertyMapping.key == "business_unit").with_for_update()
    )
    if row is None:
        row = HubspotPropertyMapping(key="business_unit", mapping_version=1)
        session.add(row)
    before = _audit_snapshot(row)
    bound = bool(row.internal_name)
    objects = [row.object_type] if bound else ["deal", "company"]
    evidence: dict[str, Any] = {
        "searched_deal_property_names": [], "searched_company_property_names": [],
        "hints_used": list(_BU_NAME_HINTS),
    }
    state, reason = "absent", "business_unit_not_found"
    hit = None
    hit_object = None
    options = None
    for obj in objects:
        try:
            if obj not in ("deal", "company"):
                raise ValueError("invalid_bound_object")
            props = await _list_properties(
                client, object_type="deals" if obj == "deal" else "companies"
            )
            evidence[f"searched_{obj}_property_names"] = [p["name"] for p in props]
            candidates = ([p for p in props if p["name"] == row.internal_name]
                          if bound else [p for p in props if _matches(p)])
            if bound and (not candidates or candidates[0]["type"] != "enumeration"):
                state, reason = "unavailable", "bound_property_missing_or_incompatible"
                break
            if len(candidates) > 1:
                state, reason = "ambiguous", "multiple_business_unit_properties"
                evidence["candidates"] = [
                    {"object_type": obj, "name": p["name"], "label": p["label"]}
                    for p in candidates
                ]
                break
            if candidates:
                hit = candidates[0]
                options = _extract_options(hit)
                hit_object = obj
                state, reason = "configured", None
                break
        except Exception as exc:
            state, reason = "unavailable", "metadata_fetch_or_schema_failed"
            evidence["error_type"] = type(exc).__name__
            evidence["failed_object"] = obj
            break

    now = datetime.now(UTC)
    row.checked_at = now
    if state == "configured":
        identity = (hit["name"], hit_object, hit["label"], hit["type"], options)
        previous = (row.internal_name, row.object_type, row.label, row.field_type,
                    sorted(row.options or [], key=lambda option: option["value"]))
        if bound and identity != previous:
            row.mapping_version += 1
        row.internal_name, row.object_type, row.label, row.field_type, row.options = identity
        evidence["matched_property"] = {
            "name": hit["name"], "label": hit["label"], "type": hit["type"],
            "object_type": hit_object, "options": options,
        }
        row.last_success_at = now
    elif state != "unavailable":
        row.last_success_at = now
    if state != "configured" and row.evidence:
        last_good = (row.evidence if "matched_property" in row.evidence
                     else row.evidence.get("last_good"))
        if last_good:
            evidence["last_good"] = last_good
    row.availability_state, row.availability_reason, row.evidence = state, reason, evidence
    await session.flush()
    after = _audit_snapshot(row)
    if before != after:
        await append_audit(
            session, actor_id=None, action="hubspot_property_mapping_changed",
            entity="hubspot_property_mapping", entity_id=row.key,
            before=before, after=after,
        )
    await touch_source(session, source="hubspot_property_business_unit",
                       success=state == "configured", error=reason)
    return DiscoveryResult(
        key=row.key, found=state == "configured", internal_name=row.internal_name,
        object_type=row.object_type, label=row.label, field_type=row.field_type,
        options=row.options, evidence=evidence, availability_state=state,
        availability_reason=reason, mapping_version=row.mapping_version,
    )


async def get_business_unit_mapping(session: AsyncSession) -> HubspotPropertyMapping | None:
    """Legacy consumer: return usable configuration only, never stale evidence."""
    row = await session.get(HubspotPropertyMapping, "business_unit")
    if row and row.availability_state == "configured":
        return row
    return None
