"""S22 P5-2 — business units, owners, rate basis, person, actuals.

engagement: business_unit (ST21 / IT Avalon / Retro Rabbit, backfilled ST21),
sales_owner, delivery_owner (free text from the model's dashboard), closed.
allocation: rate_basis (hourly / daily / monthly, default hourly), person.
allocation_actual: billed revenue and net hours per allocation-month,
unique on (allocation_id, month). Reversible.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261012_0066_bu_actuals"
down_revision = "20261012_0065_portfolio_forecast"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("engagement") as batch:
        batch.add_column(sa.Column("business_unit", sa.String(length=32), nullable=False, server_default="ST21"))
        batch.add_column(sa.Column("sales_owner", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("delivery_owner", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("closed", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_check_constraint(
            "ck_engagement_business_unit", "business_unit IN ('ST21','IT Avalon','Retro Rabbit')"
        )
    with op.batch_alter_table("allocation") as batch:
        batch.add_column(sa.Column("rate_basis", sa.String(length=16), nullable=False, server_default="hourly"))
        batch.add_column(sa.Column("person", sa.String(length=255), nullable=True))
        batch.create_check_constraint("ck_allocation_rate_basis", "rate_basis IN ('hourly','daily','monthly')")
    op.create_table(
        "allocation_actual",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("allocation_id", sa.Uuid(), sa.ForeignKey("allocation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("hours", sa.Numeric(), nullable=True),
        sa.Column("revenue", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("allocation_id", "month", name="uq_allocation_actual_month"),
    )
    op.create_index("ix_allocation_actual_allocation", "allocation_actual", ["allocation_id"])
    op.create_index("ix_engagement_business_unit", "engagement", ["business_unit", "closed"])


def downgrade() -> None:
    op.drop_index("ix_engagement_business_unit", table_name="engagement")
    op.drop_index("ix_allocation_actual_allocation", table_name="allocation_actual")
    op.drop_table("allocation_actual")
    with op.batch_alter_table("allocation") as batch:
        batch.drop_constraint("ck_allocation_rate_basis", type_="check")
        batch.drop_column("person")
        batch.drop_column("rate_basis")
    with op.batch_alter_table("engagement") as batch:
        batch.drop_constraint("ck_engagement_business_unit", type_="check")
        batch.drop_column("closed")
        batch.drop_column("delivery_owner")
        batch.drop_column("sales_owner")
        batch.drop_column("business_unit")
