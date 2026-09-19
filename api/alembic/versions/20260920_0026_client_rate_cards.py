"""client_rate_card + client_rate_card_row — S9 wave 1.

Revision ID: 20260920_0026
Revises: 20260919_0025
Create Date: 2026-09-20

Split the single "rate card" concept into three cleanly separated tables
per ``docs/sow-first-principles.md``:

- ``client_rate_card`` / ``client_rate_card_row`` (this migration) —
  per-client bill rates, versioned + effective-dated, sourced from the
  MSA rate schedule or manual entry.
- ``rate_card_version`` / ``rate_card_row`` (existing) — HR cost bands.
  Left in place under the original names; a follow-up refactor renames
  them to ``cost_band_*``.
- ``policy_version`` (existing) — margin floors + FX convention.

Rows are immutable after publish. ``source`` is one of ``msa|manual|
import``; ``source_document_id`` back-links to the uploaded MSA in the
agreements bucket (nullable for manual publishes).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_0026"
down_revision: str | None = "20260919_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_rate_card",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("notes", sa.String(length=1024), nullable=True),
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "source IN ('msa','manual','import')",
            name="ck_client_rate_card_source",
        ),
    )
    op.create_index(
        "ix_client_rate_card_client_effective",
        "client_rate_card",
        ["client_id", "effective_from"],
    )

    op.create_table(
        "client_rate_card_row",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "client_rate_card_id",
            sa.Uuid(),
            sa.ForeignKey("client_rate_card.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=128), nullable=False),
        sa.Column("seniority", sa.String(length=64), nullable=False),
        sa.Column("location", sa.String(length=16), nullable=False),
        sa.Column("bill_rate", sa.Numeric(10, 4), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="USD",
        ),
        sa.Column(
            "unit",
            sa.String(length=8),
            nullable=False,
            server_default="hourly",
        ),
        sa.Column("effective_period", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "location IN ('US','India')",
            name="ck_client_rate_card_row_location",
        ),
        sa.CheckConstraint(
            "unit IN ('hourly','daily','monthly')",
            name="ck_client_rate_card_row_unit",
        ),
    )
    op.create_index(
        "ix_client_rate_card_row_lookup",
        "client_rate_card_row",
        ["client_rate_card_id", "role", "seniority", "location"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_client_rate_card_row_lookup", table_name="client_rate_card_row"
    )
    op.drop_table("client_rate_card_row")
    op.drop_index(
        "ix_client_rate_card_client_effective", table_name="client_rate_card"
    )
    op.drop_table("client_rate_card")
