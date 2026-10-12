"""S22 P1-2 — portfolio & forecast ledger + calendar seeds.

Creates engagement, resource, allocation (with superseded_by), engagement_cost,
calendar_location, holiday, cost_rate_card, forecast_policy and forecast_run,
with the indexes the directive names: (engagement_id, start, end),
(resource_id, start, end), (superseded_by).

Seeds the calendar from the workbook's Settings tab
(docs/reference/DealGate_Cost_Margin_Sheet.xlsx): US W-2 36 %, US 1099 5 %,
India 8 %, resource floors 35 / 50, project floor 35 %, hours/day 8, the
placeholder cost rate card and the US / India weekday holidays 2026–27.
Seed ids are uuid5 of their natural key so re-running on an empty database
is deterministic. Reversible: downgrade drops every table.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261012_0065_portfolio_forecast"
down_revision = "20261006_0064_commercial_draft"
branch_labels = None
depends_on = None

_NS = uuid.UUID("5e1b2c3d-0000-4000-8000-00000000f0c5")


def _seed_id(*parts: str) -> uuid.UUID:
    return uuid.uuid5(_NS, "|".join(parts))


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


# --- workbook Settings tab ------------------------------------------------

LOCATIONS = [
    # name, burden W-2, burden 1099, resource floor
    ("US", Decimal("0.36"), Decimal("0.05"), Decimal("0.35")),
    ("India", Decimal("0.08"), Decimal("0.08"), Decimal("0.50")),
]

RATE_CARD = {
    # seniority: (US W-2, US 1099, India W-2, India 1099)
    "Junior": (60, 65, 12, 14),
    "Mid": (80, 88, 18, 20),
    "Senior": (100, 110, 25, 28),
    "Principal": (130, 145, 35, 40),
}

HOLIDAYS = {
    "US": [
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-05-25", "2026-06-19", "2026-07-03",
        "2026-09-07", "2026-10-12", "2026-11-11", "2026-11-26", "2026-12-25",
        "2027-01-01", "2027-01-18", "2027-02-15", "2027-05-31", "2027-06-18", "2027-07-05",
        "2027-09-06", "2027-10-11", "2027-11-11", "2027-11-25", "2027-12-24",
    ],
    "India": [
        "2026-01-01", "2026-01-26", "2026-08-15", "2026-10-02", "2026-12-25",
        "2027-01-01", "2027-01-26", "2027-08-15", "2027-10-02", "2027-12-25",
    ],
}


def upgrade() -> None:
    op.create_table(
        "engagement",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), sa.ForeignKey("opportunity.id", ondelete="SET NULL"), nullable=True),
        sa.Column("hubspot_deal_id", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("start", sa.Date(), nullable=False),
        sa.Column("end", sa.Date(), nullable=False),
        sa.Column("total_price", sa.Numeric(), nullable=True),
        sa.Column("monthly_fee", sa.Numeric(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("additional_costs_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("same_dates_for_all", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("owner_user_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "type IN ('fixed_cost','assessment','msp','time_and_materials','staff_augmentation')",
            name="ck_engagement_type",
        ),
    )
    op.create_index("ix_engagement_client_window", "engagement", ["client_id", "start", "end"])

    op.create_table(
        "resource",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location", sa.String(64), nullable=False),
        sa.Column("employment_type", sa.String(32), nullable=False),
        sa.Column("seniority", sa.String(32), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "allocation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("engagement_id", sa.Uuid(), sa.ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_id", sa.Uuid(), sa.ForeignKey("resource.id"), nullable=False),
        sa.Column("role", sa.String(255), nullable=False),
        sa.Column("seniority", sa.String(32), nullable=True),
        sa.Column("location", sa.String(64), nullable=False),
        sa.Column("employment_type", sa.String(32), nullable=False),
        sa.Column("assignment", sa.String(255), nullable=True),
        sa.Column("utilization", sa.Numeric(), nullable=False),
        sa.Column("bill_rate", sa.Numeric(), nullable=True),
        sa.Column("cost_per_hour", sa.Numeric(), nullable=True),
        sa.Column("start", sa.Date(), nullable=True),
        sa.Column("end", sa.Date(), nullable=True),
        sa.Column("hours_override", sa.Numeric(), nullable=True),
        sa.Column("superseded_by", sa.Uuid(), sa.ForeignKey("allocation.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_allocation_engagement_window", "allocation", ["engagement_id", "start", "end"])
    op.create_index("ix_allocation_resource_window", "allocation", ["resource_id", "start", "end"])
    op.create_index("ix_allocation_superseded_by", "allocation", ["superseded_by"])

    op.create_table(
        "engagement_cost",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("engagement_id", sa.Uuid(), sa.ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("location", sa.String(64), nullable=True),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("frequency", sa.String(16), nullable=False, server_default="one_time"),
        sa.Column("billed_to_client", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_engagement_cost_engagement_id", "engagement_cost", ["engagement_id"])

    op.create_table(
        "calendar_location",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("burden_pct_w2", sa.Numeric(), nullable=False),
        sa.Column("burden_pct_1099", sa.Numeric(), nullable=False),
        sa.Column("resource_floor_pct", sa.Numeric(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "holiday",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("location_id", sa.Uuid(), sa.ForeignKey("calendar_location.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.UniqueConstraint("location_id", "day", name="uq_holiday_location_day"),
    )

    op.create_table(
        "cost_rate_card",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("seniority", sa.String(32), nullable=False),
        sa.Column("location_id", sa.Uuid(), sa.ForeignKey("calendar_location.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employment_type", sa.String(32), nullable=False),
        sa.Column("cost_per_hour", sa.Numeric(), nullable=False),
        sa.UniqueConstraint("seniority", "location_id", "employment_type", name="uq_cost_rate_card_cell"),
    )

    op.create_table(
        "forecast_policy",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("hours_per_day", sa.Numeric(), nullable=False),
        sa.Column("project_floor_pct", sa.Numeric(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "forecast_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("engagement_id", sa.Uuid(), sa.ForeignKey("engagement.id", ondelete="CASCADE"), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("payload", _json_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_forecast_run_lookup", "forecast_run", ["engagement_id", "input_hash"])

    _seed()


def _seed() -> None:
    locations = sa.table(
        "calendar_location",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("burden_pct_w2", sa.Numeric()),
        sa.column("burden_pct_1099", sa.Numeric()),
        sa.column("resource_floor_pct", sa.Numeric()),
    )
    holidays = sa.table(
        "holiday",
        sa.column("id", sa.Uuid()),
        sa.column("location_id", sa.Uuid()),
        sa.column("day", sa.Date()),
    )
    rate_card = sa.table(
        "cost_rate_card",
        sa.column("id", sa.Uuid()),
        sa.column("seniority", sa.String()),
        sa.column("location_id", sa.Uuid()),
        sa.column("employment_type", sa.String()),
        sa.column("cost_per_hour", sa.Numeric()),
    )
    policy = sa.table(
        "forecast_policy",
        sa.column("id", sa.Uuid()),
        sa.column("hours_per_day", sa.Numeric()),
        sa.column("project_floor_pct", sa.Numeric()),
    )

    op.bulk_insert(
        locations,
        [
            {
                "id": _seed_id("location", name),
                "name": name,
                "burden_pct_w2": w2,
                "burden_pct_1099": c99,
                "resource_floor_pct": floor,
            }
            for name, w2, c99, floor in LOCATIONS
        ],
    )
    op.bulk_insert(
        holidays,
        [
            {
                "id": _seed_id("holiday", name, day),
                "location_id": _seed_id("location", name),
                "day": date.fromisoformat(day),
            }
            for name, days in HOLIDAYS.items()
            for day in days
        ],
    )
    cells = []
    for seniority, (us_w2, us_99, in_w2, in_99) in RATE_CARD.items():
        for loc, emp, value in (
            ("US", "w2_employee", us_w2),
            ("US", "contractor_1099", us_99),
            ("India", "w2_employee", in_w2),
            ("India", "contractor_1099", in_99),
        ):
            cells.append(
                {
                    "id": _seed_id("rate", seniority, loc, emp),
                    "seniority": seniority,
                    "location_id": _seed_id("location", loc),
                    "employment_type": emp,
                    "cost_per_hour": Decimal(value),
                }
            )
    op.bulk_insert(rate_card, cells)
    op.bulk_insert(
        policy,
        [
            {
                "id": _seed_id("policy", "default"),
                "hours_per_day": Decimal("8"),
                "project_floor_pct": Decimal("0.35"),
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_forecast_run_lookup", table_name="forecast_run")
    op.drop_table("forecast_run")
    op.drop_table("forecast_policy")
    op.drop_table("cost_rate_card")
    op.drop_table("holiday")
    op.drop_table("calendar_location")
    op.drop_index("ix_engagement_cost_engagement_id", table_name="engagement_cost")
    op.drop_table("engagement_cost")
    op.drop_index("ix_allocation_superseded_by", table_name="allocation")
    op.drop_index("ix_allocation_resource_window", table_name="allocation")
    op.drop_index("ix_allocation_engagement_window", table_name="allocation")
    op.drop_table("allocation")
    op.drop_table("resource")
    op.drop_index("ix_engagement_client_window", table_name="engagement")
    op.drop_table("engagement")
