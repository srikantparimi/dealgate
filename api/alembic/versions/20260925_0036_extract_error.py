"""S15: preserve the extract failure reason on sow_version.

Before this migration, when Bedrock returned ManualRequired (bad model id,
throttle, schema-validation reject, ...) the pipeline stashed the reason in
a local ``warnings`` list that ``sow_upload_job_service`` dropped on the
floor. The confirm page then presented one silent pipeline failure as
fifteen per-field problems (see docs/directives/s15-confirm-page-integrity.md).

Adding an ``extract_error`` column so the reason lives with the version and
the UI can render an honest "We couldn't read this document (reason)" banner
plus a Retry button.

Revision ID: 20260925_0036_extract_error
Revises: 20260924_0035_dc_settings
"""

from alembic import op
import sqlalchemy as sa


revision = "20260925_0036_extract_error"
down_revision = "20260924_0035_dc_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sow_version",
        sa.Column("extract_error", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sow_version", "extract_error")
