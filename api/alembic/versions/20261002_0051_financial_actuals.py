"""Immutable source-revision financial facts, independent of source-SOW deletion."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261002_0051_financial_actuals"
down_revision = "20261002_0050_forecast_plans"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("financial_import_batch",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("source_system", sa.String(128), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("errors", JSONB()),
        sa.Column("test_fixture", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("tenant_id", "environment", "source_system", "request_key", name="uq_financial_import_request"))
    op.create_table("financial_actual",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("source_system", sa.String(128), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), sa.ForeignKey("financial_import_batch.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("client.id", ondelete="SET NULL")),
        sa.Column("original_account_id", sa.Uuid(), nullable=False),
        sa.Column("gm_model_id", sa.Uuid(), sa.ForeignKey("gm_model.id", ondelete="SET NULL")),
        sa.Column("original_gm_model_id", sa.Uuid()),
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("measure", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=False),
        sa.Column("fx_rate", sa.Numeric()),
        sa.Column("fx_version", sa.String(128)),
        sa.Column("fx_date", sa.Date()),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("test_fixture", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "environment", "source_system", "source_id", "revision", name="uq_financial_actual_revision"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM financial_import_batch)")).scalar():
        raise RuntimeError("Cannot discard financial import history during downgrade")
    op.drop_table("financial_actual")
    op.drop_table("financial_import_batch")
