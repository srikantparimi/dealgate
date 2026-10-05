"""Expand persistent scan state; retain legacy stage identity until writer cutover."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261002_0055_scan_state"
down_revision = "20261002_0054_source_facts"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("sync_status", "scan_generation", existing_type=sa.Integer(), type_=sa.BigInteger())
    op.add_column("sync_status", sa.Column("scan_phase", sa.String(16), nullable=False, server_default="idle"))
    op.add_column("sync_status", sa.Column("scan_failure_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sync_status", sa.Column("scan_context", postgresql.JSONB(), nullable=True))
    op.add_column("sync_status", sa.Column("scan_lease_token", sa.Uuid(), nullable=True))
    op.add_column("sync_status", sa.Column("scan_lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_sync_scan_phase", "sync_status",
        "scan_phase IN ('idle','scanning','finalizing','completed','failed')")
    op.create_check_constraint("ck_sync_scan_failures", "sync_status", "scan_failure_count >= 0")
    op.create_check_constraint("ck_sync_scan_generation", "sync_status", "scan_generation IS NULL OR scan_generation >= 0")
    op.add_column("opportunity", sa.Column("hubspot_seen_generation", sa.BigInteger(), nullable=True))
    op.create_unique_constraint("uq_hubspot_stage_pipeline_id", "hubspot_stage", ["pipeline_id", "id"])


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS(SELECT 1 FROM sync_status WHERE "
        "scan_phase <> 'idle' OR scan_failure_count <> 0 OR scan_context IS NOT NULL "
        "OR scan_lease_token IS NOT NULL OR scan_lease_expires_at IS NOT NULL "
        "OR scan_generation > 2147483647)")).scalar():
        raise RuntimeError("Cannot discard scan recovery evidence or truncate generation")
    if bind.execute(sa.text("SELECT EXISTS(SELECT 1 FROM opportunity WHERE hubspot_seen_generation IS NOT NULL)")).scalar():
        raise RuntimeError("Cannot discard observed scan generation")
    op.drop_constraint("uq_hubspot_stage_pipeline_id", "hubspot_stage", type_="unique")
    op.drop_column("opportunity", "hubspot_seen_generation")
    for name in ("ck_sync_scan_generation", "ck_sync_scan_failures", "ck_sync_scan_phase"):
        op.drop_constraint(name, "sync_status", type_="check")
    for name in ("scan_lease_expires_at", "scan_lease_token", "scan_context", "scan_failure_count", "scan_phase"):
        op.drop_column("sync_status", name)
    op.alter_column("sync_status", "scan_generation", existing_type=sa.BigInteger(), type_=sa.Integer())
