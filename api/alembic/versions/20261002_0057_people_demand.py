"""Expand immutable cost-free demand publication and source-owned lines."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261002_0057_people_demand"
down_revision = "20261002_0056_people_supply"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("demand_publication",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("test_fixture", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("forecast_plan.id", ondelete="CASCADE")),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("project.id", ondelete="CASCADE")),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("client.id", ondelete="SET NULL")),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "environment", "plan_id", name="uq_demand_publication_plan"),
        sa.UniqueConstraint("tenant_id", "environment", "project_id", name="uq_demand_publication_project"),
        sa.CheckConstraint("(plan_id IS NOT NULL AND project_id IS NULL) OR (plan_id IS NULL AND project_id IS NOT NULL)", name="ck_demand_publication_source"))
    op.create_table("demand_publication_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("publication_id", sa.Uuid(), sa.ForeignKey("demand_publication.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_version", sa.String(128), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("missing", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("publication_id", "version", name="uq_demand_publication_version"),
        sa.UniqueConstraint("publication_id", "request_key", name="uq_demand_publication_request"),
        sa.CheckConstraint("version > 0", name="ck_demand_publication_revision"))
    op.create_table("demand_line",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("demand_publication_version.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_key", sa.String(255), nullable=False),
        sa.Column("component_id", sa.String(255), nullable=False),
        sa.Column("assignment_id", sa.String(255), nullable=False),
        sa.Column("role", sa.String(128), nullable=False),
        sa.Column("skills", postgresql.JSONB(), nullable=False),
        sa.Column("level", sa.String(128), nullable=False),
        sa.Column("location", sa.String(128), nullable=False),
        sa.Column("timezone", sa.String(128), nullable=False),
        sa.Column("quantity", sa.Integer()),
        sa.Column("allocation", sa.Numeric()),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("delivery_model", sa.String(64), nullable=False),
        sa.Column("retained_person_ids", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("missing", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("version_id", "line_key", name="uq_demand_line_version_key"),
        sa.CheckConstraint("quantity IS NULL OR quantity > 0", name="ck_demand_line_quantity"),
        sa.CheckConstraint("allocation IS NULL OR (CAST(allocation AS NUMERIC) > 0 AND CAST(allocation AS NUMERIC) <= 1)", name="ck_demand_line_allocation"),
        sa.CheckConstraint("start_date IS NULL OR end_date IS NULL OR end_date >= start_date", name="ck_demand_line_dates"))
    op.create_index("ix_demand_line_version_id", "demand_line", ["version_id"])


def downgrade():
    bind = op.get_bind()
    for table in ("demand_publication", "demand_publication_version", "demand_line"):
        if bind.execute(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("Cannot discard demand publication history")
    for table in ("demand_line", "demand_publication_version", "demand_publication"):
        op.drop_table(table)
