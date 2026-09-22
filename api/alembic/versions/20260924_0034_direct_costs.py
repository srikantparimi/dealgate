"""S13b: versioned direct-cost bases, pass-through and provenance."""

from alembic import op
import sqlalchemy as sa

revision = "20260924_0034_direct_costs"
down_revision = "20260924_0033"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("gm_model", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("gm_model", sa.Column("direct_costs_reviewed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("""WITH versions AS (
        SELECT id, ROW_NUMBER() OVER (PARTITION BY opportunity_id ORDER BY created_at, id) AS number
        FROM gm_model
    ) UPDATE gm_model SET version = versions.number FROM versions WHERE gm_model.id = versions.id""")
    op.alter_column("cost_line", "amount", type_=sa.Numeric(28, 12), existing_type=sa.Numeric(14, 2))
    op.add_column("cost_line", sa.Column("basis", sa.String(24), nullable=False, server_default="amount"))
    op.add_column("cost_line", sa.Column("basis_value", sa.Numeric(28, 12), nullable=True))
    op.add_column("cost_line", sa.Column("reimbursable", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("cost_line", sa.Column("provenance", sa.String(16), nullable=False, server_default="manual"))
    op.add_column("cost_line", sa.Column("source_ref", sa.String(255), nullable=True))


def downgrade():
    for name in ("source_ref", "provenance", "reimbursable", "basis_value", "basis"):
        op.drop_column("cost_line", name)
    op.alter_column("cost_line", "amount", type_=sa.Numeric(14, 2), existing_type=sa.Numeric(28, 12))
    op.drop_column("gm_model", "version")
    op.drop_column("gm_model", "direct_costs_reviewed")
