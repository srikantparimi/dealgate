"""rate_card_version, rate_card_row, policy_version — S2 E4.

Revision ID: 20260918_0002
Revises: 20260917_0001
Create Date: 2026-09-18

Finance-owned reference data: planning cost bands + margin floors. Rows are
immutable after publish (enforced in the service layer; the application role
in staging/prod should hold only SELECT + INSERT on these tables — DDL grants
land in infra, not here).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0002b"
down_revision: str | None = "20260918_0002a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_card_version",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=1024), nullable=True),
    )
    op.create_index(
        "ix_rate_card_version_effective_from",
        "rate_card_version",
        ["effective_from"],
    )

    op.create_table(
        "rate_card_row",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "rate_card_version_id",
            sa.Uuid(),
            sa.ForeignKey("rate_card_version.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=128), nullable=False),
        sa.Column("seniority", sa.String(length=64), nullable=False),
        sa.Column("location", sa.String(length=16), nullable=False),
        sa.Column("cost_low", sa.Numeric(14, 2), nullable=False),
        sa.Column("cost_base", sa.Numeric(14, 2), nullable=False),
        sa.Column("cost_high", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index(
        "ix_rate_card_row_version",
        "rate_card_row",
        ["rate_card_version_id"],
    )
    op.create_index(
        "ix_rate_card_row_lookup",
        "rate_card_row",
        ["rate_card_version_id", "role", "seniority", "location"],
    )

    op.create_table(
        "policy_version",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("us_floor", sa.Numeric(6, 4), nullable=False),
        sa.Column("india_floor", sa.Numeric(6, 4), nullable=False),
        sa.Column("fx_convention", sa.String(length=64), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=1024), nullable=True),
    )
    op.create_index(
        "ix_policy_version_effective_from",
        "policy_version",
        ["effective_from"],
    )


def downgrade() -> None:
    op.drop_index("ix_policy_version_effective_from", table_name="policy_version")
    op.drop_table("policy_version")
    op.drop_index("ix_rate_card_row_lookup", table_name="rate_card_row")
    op.drop_index("ix_rate_card_row_version", table_name="rate_card_row")
    op.drop_table("rate_card_row")
    op.drop_index("ix_rate_card_version_effective_from", table_name="rate_card_version")
    op.drop_table("rate_card_version")
