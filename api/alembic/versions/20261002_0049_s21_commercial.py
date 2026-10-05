"""Immutable typed commercial inputs and assessed snapshot on existing GM versions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261002_0049_s21_commercial"
down_revision = "20261002_0048_s21_sales"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("gm_model", sa.Column("commercial_inputs", postgresql.JSONB(), nullable=True))
    op.add_column("gm_model", sa.Column("commercial_snapshot", postgresql.JSONB(), nullable=True))
    for column in ("revenue_us", "revenue_india"):
        op.alter_column("gm_model", column, existing_type=sa.Numeric(14, 2),
                        type_=sa.Numeric(), nullable=True)


def downgrade():
    if op.get_bind().execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM gm_model WHERE commercial_inputs IS NOT NULL "
        "OR revenue_us IS NULL OR revenue_india IS NULL "
        "OR revenue_us != round(revenue_us, 2) OR revenue_india != round(revenue_india, 2) "
        "OR abs(revenue_us) >= 1000000000000 OR abs(revenue_india) >= 1000000000000)"
    )).scalar():
        raise RuntimeError("Cannot discard commercial history or narrow monetary precision")
    for column in ("revenue_us", "revenue_india"):
        op.alter_column("gm_model", column, existing_type=sa.Numeric(),
                        type_=sa.Numeric(14, 2), nullable=False)
    op.drop_column("gm_model", "commercial_snapshot")
    op.drop_column("gm_model", "commercial_inputs")
