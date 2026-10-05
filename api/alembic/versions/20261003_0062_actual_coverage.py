"""Preserve Finance-confirmed service coverage with immutable actual revisions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261003_0062_actual_coverage"
down_revision = "20261002_0061_automation_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("financial_actual", sa.Column("coverage", JSONB(), nullable=True))


def downgrade():
    if op.get_bind().execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM financial_actual WHERE coverage IS NOT NULL AND coverage <> 'null'::jsonb)"
    )).scalar():
        raise RuntimeError("Cannot discard immutable financial coverage history")
    op.drop_column("financial_actual", "coverage")
