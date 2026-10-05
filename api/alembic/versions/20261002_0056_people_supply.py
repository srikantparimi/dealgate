"""Expand cost-free immutable managed workforce supply snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261002_0056_people_supply"
down_revision = "20261002_0055_scan_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("people_source",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("source_system", sa.String(128), nullable=False),
        sa.Column("test_fixture", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "environment", "source_system", "test_fixture", name="uq_people_source_scope"))
    op.create_table("people_import_batch",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("people_source.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("source_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("imported_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("person_count", sa.Integer(), nullable=False),
        sa.Column("previous_batch_id", sa.Uuid(), sa.ForeignKey("people_import_batch.id")),
        sa.UniqueConstraint("source_id", "revision", name="uq_people_batch_revision"),
        sa.UniqueConstraint("source_id", "request_key", name="uq_people_batch_request"),
        sa.UniqueConstraint("id", "source_id", name="uq_people_batch_source"),
        sa.CheckConstraint("revision > 0 AND person_count >= 0", name="ck_people_batch_counts"))
    op.create_table("workforce_person",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("people_source.id"), nullable=False),
        sa.Column("person_key", sa.String(255), nullable=False),
        sa.UniqueConstraint("source_id", "person_key", name="uq_workforce_person_source_key"),
        sa.UniqueConstraint("id", "source_id", name="uq_workforce_person_source"))
    op.create_table("workforce_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(128), nullable=False),
        sa.Column("skills", postgresql.JSONB(), nullable=False),
        sa.Column("level", sa.String(128), nullable=False),
        sa.Column("location", sa.String(128), nullable=False),
        sa.Column("timezone", sa.String(128), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("person_id", "batch_id", name="uq_workforce_version_snapshot"),
        sa.ForeignKeyConstraint(["person_id", "source_id"], ["workforce_person.id", "workforce_person.source_id"], name="fk_workforce_version_person_source"),
        sa.ForeignKeyConstraint(["batch_id", "source_id"], ["people_import_batch.id", "people_import_batch.source_id"], name="fk_workforce_version_batch_source"))
    op.create_index("ix_workforce_version_batch_id", "workforce_version", ["batch_id"])
    op.create_table("workforce_interval",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("workforce_version.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("assignment_key", sa.String(255)),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("allocation", sa.Numeric(), nullable=False),
        sa.CheckConstraint("allocation > 0 AND allocation <= 1", name="ck_workforce_interval_allocation"),
        sa.CheckConstraint("end_date >= start_date", name="ck_workforce_interval_dates"),
        sa.CheckConstraint("(kind = 'gross' AND assignment_key IS NULL) OR "
            "(kind IN ('committed','reserved','hired') AND assignment_key IS NOT NULL)", name="ck_workforce_interval_basis"))
    op.create_index("ix_workforce_interval_version_id", "workforce_interval", ["version_id"])


def downgrade():
    bind = op.get_bind()
    for table in ("people_source", "people_import_batch", "workforce_person", "workforce_version", "workforce_interval"):
        if bind.execute(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("Cannot discard managed workforce source or snapshot evidence")
    for table in ("workforce_interval", "workforce_version", "workforce_person", "people_import_batch", "people_source"):
        op.drop_table(table)
