"""S23-PL2 B3 — HubSpot region value → business unit and display region.

Deals carry HubSpot region values ("US", "South Africa", …), not business
units. This table says which business unit each value means and which region
to show beside it; "US" holds two business units, so a business unit is never
shown without its region. Rows are read at request time, so an edit changes
every deal with that value immediately.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

BUSINESS_UNITS = ("ST21", "IT Avalon", "Retro Rabbit")

# The seed migration 0070 writes; tests seed the same rows.
DEFAULT_REGION_MAP: tuple[dict[str, str | None], ...] = (
    {"hubspot_value": "South Africa", "business_unit": "Retro Rabbit", "region": "South Africa", "note": None},
    {"hubspot_value": "US - IT Avalon (Staffing)", "business_unit": "IT Avalon", "region": "US", "note": "Staffing"},
    {"hubspot_value": "US - IT Avalon", "business_unit": "IT Avalon", "region": "US", "note": None},
    {"hubspot_value": "US", "business_unit": "ST21", "region": "US", "note": None},
)


class HubspotRegionMap(Base):
    __tablename__ = "hubspot_region_map"
    __table_args__ = (
        CheckConstraint(
            "business_unit IN ('ST21','IT Avalon','Retro Rabbit')",
            name="ck_hubspot_region_map_business_unit",
        ),
    )

    hubspot_value: Mapped[str] = mapped_column(String(255), primary_key=True)
    business_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("user.id"), nullable=True)
