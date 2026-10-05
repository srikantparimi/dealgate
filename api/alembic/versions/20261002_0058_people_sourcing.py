"""Persist scoped sourcing rules and source-bound immutable proposal history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261002_0058_people_sourcing"
down_revision = "20261002_0057_people_demand"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("sourcing_rule_set",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("test_fixture", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("tenant_id", "environment", "test_fixture", name="uq_sourcing_rule_scope"))
    op.create_table("sourcing_rule_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rule_set_id", sa.Uuid(), sa.ForeignKey("sourcing_rule_set.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("rule_set_id", "revision", name="uq_sourcing_rule_revision"),
        sa.UniqueConstraint("rule_set_id", "request_key", name="uq_sourcing_rule_request"),
        sa.CheckConstraint("revision > 0", name="ck_sourcing_rule_revision"))
    op.create_table("sourcing_draft",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("publication_id", sa.Uuid(), sa.ForeignKey("demand_publication.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("publication_id", name="uq_sourcing_draft_publication"))
    op.create_table("sourcing_draft_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("draft_id", sa.Uuid(), sa.ForeignKey("sourcing_draft.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("demand_version_id", sa.Uuid(), sa.ForeignKey("demand_publication_version.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_version_id", sa.Uuid(), sa.ForeignKey("sourcing_rule_version.id"), nullable=False),
        sa.Column("source_watermark", sa.String(64), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("draft_id", "revision", name="uq_sourcing_draft_revision"),
        sa.UniqueConstraint("draft_id", "request_key", name="uq_sourcing_draft_request"),
        sa.CheckConstraint("revision > 0", name="ck_sourcing_draft_revision"))


def downgrade():
    bind = op.get_bind()
    for table in ("sourcing_rule_set", "sourcing_rule_version", "sourcing_draft", "sourcing_draft_version"):
        if bind.execute(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("Cannot discard sourcing history")
    for table in ("sourcing_draft_version", "sourcing_draft", "sourcing_rule_version", "sourcing_rule_set"):
        op.drop_table(table)
