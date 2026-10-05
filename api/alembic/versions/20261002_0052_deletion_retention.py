"""Durable deletion fences and retained project/actual source links."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261002_0052_deletion_retention"
down_revision = "20261002_0051_financial_actuals"
branch_labels = None
depends_on = None

LINKS = {
    "project": {"opportunity_id": "opportunity", "sow_version_id": "sow_version",
                "gm_model_id": "gm_model", "package_id": "approval_package", "client_id": "client"},
    "actual_period": {"gm_model_id": "gm_model", "resource_line_id": "resource_line"},
}


def relink(table, column, target, *, retained):
    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys(table)
    fk = next(fk for fk in foreign_keys if fk["constrained_columns"] == [column])
    op.drop_constraint(fk["name"], table, type_="foreignkey")
    op.alter_column(table, column, existing_type=sa.Uuid(), nullable=retained or column == "client_id")
    op.create_foreign_key(fk["name"], table, target, [column], ["id"], ondelete="SET NULL" if retained else None)


def upgrade():
    op.add_column("project", sa.Column("source_deleted_at", sa.DateTime(timezone=True)))
    op.add_column("project", sa.Column("retained_source", JSONB()))
    op.add_column("actual_period", sa.Column("original_gm_model_id", sa.Uuid()))
    op.add_column("actual_period", sa.Column("original_resource_line_id", sa.Uuid()))
    op.add_column("actual_period", sa.Column("source_deleted_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE actual_period SET original_gm_model_id=gm_model_id, original_resource_line_id=resource_line_id")
    for table, columns in LINKS.items():
        for column, target in columns.items():
            relink(table, column, target, retained=True)
    op.create_table("deletion_job",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("sow_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid()),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("user.id")),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("summary", JSONB(), nullable=False),
        sa.Column("objects", JSONB(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(1024)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "environment", "sow_id", name="uq_deletion_sow"))
    op.create_table("deletion_fence",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("environment", sa.String(32), primary_key=True),
        sa.Column("subject_type", sa.String(32), primary_key=True),
        sa.Column("subject_id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("deletion_job.id"), nullable=False))


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT EXISTS(SELECT 1 FROM deletion_job)")).scalar():
        raise RuntimeError("Cannot discard deletion fences or cleanup history")
    for table, columns in LINKS.items():
        for column, target in columns.items():
            if column != "client_id" and connection.execute(sa.text(
                f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {column} IS NULL)"
            )).scalar():
                raise RuntimeError("Cannot restore required links on retained financial records")
            relink(table, column, target, retained=False)
    op.drop_table("deletion_fence")
    op.drop_table("deletion_job")
    op.drop_column("project", "retained_source")
    op.drop_column("project", "source_deleted_at")
    for column in ("original_gm_model_id", "original_resource_line_id", "source_deleted_at"):
        op.drop_column("actual_period", column)
