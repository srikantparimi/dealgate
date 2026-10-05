"""Preserve explicit staffing-slot conversion independently of financial fractions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261002_0059_demand_coverage"
down_revision = "20261002_0058_people_sourcing"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("demand_coverage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("test_fixture", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("plan_publication_id", sa.Uuid(), sa.ForeignKey("demand_publication.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_publication_id", sa.Uuid(), sa.ForeignKey("demand_publication.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("tenant_id", "environment", "plan_publication_id", "project_publication_id", name="uq_demand_coverage_pair"),
        sa.CheckConstraint("plan_publication_id <> project_publication_id", name="ck_demand_coverage_pair"))
    op.create_table("demand_coverage_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("root_id", sa.Uuid(), sa.ForeignKey("demand_coverage.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("plan_version_id", sa.Uuid(), sa.ForeignKey("demand_publication_version.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_version_id", sa.Uuid(), sa.ForeignKey("demand_publication_version.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mappings", postgresql.JSONB(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("root_id", "revision", name="uq_demand_coverage_revision"),
        sa.UniqueConstraint("root_id", "request_key", name="uq_demand_coverage_request"),
        sa.CheckConstraint("revision > 0", name="ck_demand_coverage_revision"))


def downgrade():
    for table in ("demand_coverage", "demand_coverage_version"):
        if op.get_bind().execute(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("Cannot discard staffing coverage history")
    op.drop_table("demand_coverage_version")
    op.drop_table("demand_coverage")
