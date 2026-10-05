"""Versioned, explicitly opted-in sourcing automation authority."""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0060_automation_rules"
down_revision = "20261002_0059_demand_coverage"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("automation_rule",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("test_fixture", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("domain", sa.String(64), nullable=False),
        sa.UniqueConstraint("tenant_id", "environment", "test_fixture", "domain", name="uq_automation_rule_scope"),
        sa.CheckConstraint("domain = 'sourcing_refresh'", name="ck_automation_rule_domain"))
    op.create_table("automation_rule_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rule_id", sa.Uuid(), sa.ForeignKey("automation_rule.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("source_scope", sa.String(64), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("rule_id", "revision", name="uq_automation_rule_revision"),
        sa.UniqueConstraint("rule_id", "request_key", name="uq_automation_rule_request"),
        sa.CheckConstraint("revision > 0", name="ck_automation_rule_revision"),
        sa.CheckConstraint("source_scope = 'authorized_sources'", name="ck_automation_rule_source_scope"))


def downgrade():
    for table in ("automation_rule", "automation_rule_version"):
        if op.get_bind().execute(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("Cannot discard automation authority history")
    op.drop_table("automation_rule_version")
    op.drop_table("automation_rule")
