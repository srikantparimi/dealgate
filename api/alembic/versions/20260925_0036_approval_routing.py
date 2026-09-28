"""S14b approval routing and condition evidence.

Revision ID: 20260925_0036_approval_routing
Revises: 20260924_0035_dc_settings
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260925_0036_approval_routing"
down_revision = "20260924_0035_dc_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approval_group",
        sa.Column("function", sa.String(32), primary_key=True),
        sa.Column("member_ids", postgresql.JSONB(), nullable=False),
        sa.Column("backup_ids", postgresql.JSONB(), nullable=False),
        sa.Column("default_approver_id", sa.Uuid(), sa.ForeignKey("user.id")),
    )
    op.create_table(
        "approval_assignment",
        sa.Column("package_id", sa.Uuid(), sa.ForeignKey("approval_package.id"), primary_key=True),
        sa.Column("function", sa.String(32), primary_key=True),
        sa.Column("approver_id", sa.Uuid(), sa.ForeignKey("user.id")),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("use_sla", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("task.id")),
    )
    op.create_table(
        "approval_condition_evidence",
        sa.Column("package_id", sa.Uuid(), sa.ForeignKey("approval_package.id"), primary_key=True),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("approval_condition_evidence")
    op.drop_table("approval_assignment")
    op.drop_table("approval_group")
