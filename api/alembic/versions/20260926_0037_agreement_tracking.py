"""S16 agreement tracking, preserving all historical rows and states."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260926_0037"
down_revision = "20260925_0036_extract_error"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agreement_gap",
        sa.Column("legal_entity_id", sa.Uuid(), sa.ForeignKey("legal_entity.id"), primary_key=True),
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("task.id"), nullable=False),
    )
    op.create_table(
        "agreement_document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agreement_id", sa.Uuid(), sa.ForeignKey("agreement.id"), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("file_s3_key", sa.String(1024), nullable=False),
        sa.Column(
            "extracted_fields",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("agreement_id", "file_hash", name="uq_agreement_document_hash"),
    )


def downgrade():
    op.drop_table("agreement_document")
    op.drop_table("agreement_gap")
