"""Transactional, source-bound sourcing refresh outbox."""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0061_automation_jobs"
down_revision = "20261002_0060_automation_rules"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("automation_job",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rule_version_id", sa.Uuid(), sa.ForeignKey("automation_rule_version.id"), nullable=False),
        sa.Column("plan_version_id", sa.Uuid(), sa.ForeignKey("forecast_plan_version.id", ondelete="CASCADE")),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("project.id", ondelete="CASCADE")),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("source_version", sa.String(64), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(1024)),
        sa.Column("result_version_id", sa.Uuid(), sa.ForeignKey("sourcing_draft_version.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("rule_version_id", "source_key", "event_key", name="uq_automation_job_event"),
        sa.CheckConstraint("(plan_version_id IS NOT NULL AND project_id IS NULL) OR "
            "(plan_version_id IS NULL AND project_id IS NOT NULL)", name="ck_automation_job_source"),
        sa.CheckConstraint("attempts >= 0", name="ck_automation_job_attempts"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT EXISTS(SELECT 1 FROM automation_job)")).scalar():
        raise RuntimeError("Cannot discard automation execution history")
    op.drop_table("automation_job")
