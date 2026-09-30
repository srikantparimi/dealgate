"""S20 W6 · watched_item table (per-user watchlist for deals + clients)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260930_0047_w6_watch"
down_revision: str | Sequence[str] | None = "20260930_0046_w2_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watched_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "kind", "item_id", name="uq_watched_item_user_kind_item"
        ),
        sa.CheckConstraint(
            "kind in ('opportunity','client')", name="ck_watched_item_kind"
        ),
    )
    op.create_index("ix_watched_item_user_kind", "watched_item", ["user_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_watched_item_user_kind", table_name="watched_item")
    op.drop_table("watched_item")
