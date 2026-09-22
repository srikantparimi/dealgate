"""Configurable direct-cost category choices.

Revision ID: 20260924_0035_dc_settings
Revises: 20260924_0034_direct_costs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260924_0035_dc_settings"
down_revision = "20260924_0034_direct_costs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "direct_cost_settings",
        sa.Column("key", sa.String(32), primary_key=True),
        sa.Column("categories", postgresql.JSONB(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("direct_cost_settings")
