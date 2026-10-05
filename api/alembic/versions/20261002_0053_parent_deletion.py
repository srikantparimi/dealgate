"""Explicit scoped subjects for retained client/opportunity deletion jobs."""

from alembic import op
import sqlalchemy as sa

revision = "20261002_0053_parent_deletion"
down_revision = "20261002_0052_deletion_retention"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("deletion_job", sa.Column("subject_type", sa.String(32), nullable=False, server_default="sow"))
    op.add_column("deletion_job", sa.Column("subject_id", sa.Uuid()))
    op.execute("UPDATE deletion_job SET subject_id=sow_id")
    op.alter_column("deletion_job", "subject_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("deletion_job", "sow_id", existing_type=sa.Uuid(), nullable=True)
    op.create_unique_constraint("uq_deletion_subject", "deletion_job",
        ["tenant_id", "environment", "subject_type", "subject_id"])


def downgrade():
    if op.get_bind().execute(sa.text(
        "SELECT EXISTS(SELECT 1 FROM deletion_job WHERE subject_type <> 'sow' OR sow_id IS NULL)"
    )).scalar():
        raise RuntimeError("Cannot discard parent deletion history")
    op.drop_constraint("uq_deletion_subject", "deletion_job", type_="unique")
    op.alter_column("deletion_job", "sow_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("deletion_job", "subject_id")
    op.drop_column("deletion_job", "subject_type")
