"""Versioned planning, schedules, conversion scope and transactional calculation jobs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261002_0050_forecast_plans"
down_revision = "20261002_0049_s21_commercial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("forecast_plan",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("client.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), sa.ForeignKey("opportunity.id", ondelete="SET NULL")),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "environment", "request_key", name="uq_forecast_plan_request"))
    op.create_table("forecast_plan_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("forecast_plan.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("scope_id", sa.String(255), nullable=False),
        sa.Column("lifecycle", sa.String(32), nullable=False),
        sa.Column("probability", sa.Numeric()),
        sa.Column("probability_source", sa.String(2000)),
        sa.Column("assumptions", JSONB(), nullable=False),
        sa.Column("component_inputs", JSONB(), nullable=False),
        sa.Column("policy_snapshot", JSONB(), nullable=False),
        sa.Column("scenario_group", sa.String(255)),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("fx_rate", sa.Numeric()),
        sa.Column("fx_version", sa.String(128)),
        sa.Column("fx_date", sa.Date()),
        sa.Column("change_reason", sa.String(2000), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("plan_id", "version", name="uq_forecast_plan_version"))
    op.create_table("forecast_schedule",
        sa.Column("plan_version_id", sa.Uuid(), sa.ForeignKey("forecast_plan_version.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("calculation_version", sa.String(64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("forecast_job",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("plan_version_id", sa.Uuid(), sa.ForeignKey("forecast_plan_version.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(1024)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_table("forecast_conversion",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("forecast_plan.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gm_model_id", sa.Uuid(), sa.ForeignKey("gm_model.id", ondelete="SET NULL")),
        sa.Column("scope_fraction", sa.Numeric(), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("plan_id", "gm_model_id", name="uq_forecast_conversion_source"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM forecast_plan)")).scalar():
        raise RuntimeError("Cannot discard Forecast planning history during downgrade")
    for name in ("forecast_conversion", "forecast_job", "forecast_schedule", "forecast_plan_version", "forecast_plan"):
        op.drop_table(name)
