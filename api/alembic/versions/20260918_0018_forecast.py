"""S6 E9 — forecast_period (weekly forecast update).

Revision ID: 20260918_0018
Revises: 20260918_0017
Create Date: 2026-09-18

Creates ``forecast_period``: one immutable row per (gm_model_id, week_ending)
capturing the Delivery lead's weekly remaining-hours snapshot plus the
forecast revenue/cost/GM computed from it via the ratified ``app.gm``
library. Immutable per week (CLAUDE.md rule 4) — enforced by a UNIQUE
constraint and by the service layer refusing PATCH.

Money columns follow rule 2: ``NUMERIC(14,2)`` for revenue/cost totals,
``NUMERIC(6,4)`` for GM ratios. ``forecast_lines_json`` stores the full
per-line remaining-hours snapshot so the trend view can replay any week's
inputs without joining ``resource_line``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260918_0018"
down_revision: str | Sequence[str] | None = "20260918_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def upgrade() -> None:
    op.create_table(
        "forecast_period",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "gm_model_id",
            sa.Uuid(),
            sa.ForeignKey("gm_model.id", name="fk_forecast_period_gm_model_id"),
            nullable=False,
        ),
        sa.Column("week_ending", sa.Date(), nullable=False),
        sa.Column("forecast_lines_json", _json_type(), nullable=False),
        sa.Column("forecast_revenue", sa.Numeric(14, 2), nullable=False),
        sa.Column("forecast_cost_us", sa.Numeric(14, 2), nullable=False),
        sa.Column("forecast_cost_india", sa.Numeric(14, 2), nullable=False),
        sa.Column("forecast_gm_us", sa.Numeric(6, 4), nullable=True),
        sa.Column("forecast_gm_india", sa.Numeric(6, 4), nullable=True),
        sa.Column(
            "updated_by",
            sa.Uuid(),
            sa.ForeignKey("user.id", name="fk_forecast_period_updated_by"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "gm_model_id", "week_ending", name="uq_forecast_period_gm_week"
        ),
    )
    op.create_index(
        "ix_forecast_period_gm_model_id",
        "forecast_period",
        ["gm_model_id", "week_ending"],
    )


def downgrade() -> None:
    op.drop_index("ix_forecast_period_gm_model_id", table_name="forecast_period")
    op.drop_table("forecast_period")
