"""Client document replacement retains immutable file revisions."""
from alembic import op
import sqlalchemy as sa

revision = "20261003_0063_agreement_versions"
down_revision = "20261003_0062_actual_coverage"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agreement", sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("ck_agreement_version", "agreement", "version_no > 0")
    op.create_table("agreement_file_version",
        sa.Column("agreement_id", sa.Uuid(), sa.ForeignKey("agreement.id"), primary_key=True),
        sa.Column("version_no", sa.Integer(), primary_key=True),
        sa.Column("file_key", sa.String(1024), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("version_no > 0", name="ck_agreement_file_version_positive"))
    op.execute("""INSERT INTO agreement_file_version
        (agreement_id, version_no, file_key, filename, file_size, uploaded_by, uploaded_at)
        SELECT id, 1, file_key, filename, file_size, uploaded_by, uploaded_at FROM agreement""")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM agreement_file_version WHERE version_no > 1 OR file_hash IS NOT NULL")).scalar():
        raise RuntimeError("Agreement revision/hash history exists; downgrade would discard evidence")
    op.drop_table("agreement_file_version")
    op.drop_constraint("ck_agreement_version", "agreement", type_="check")
    op.drop_column("agreement", "version_no")
