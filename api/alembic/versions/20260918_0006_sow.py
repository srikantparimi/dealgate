"""S3-E5: SOW upload + AI extraction + human confirm.

Two tables land here — deliberately narrow so the story is a self-contained
vertical slice (build-guide §6.3):

- ``sow`` — one row per opportunity (unique FK). The row is the parent that
  anchors every uploaded file version. Immutable.
- ``sow_version`` — one row per uploaded PDF/DOCX. Rows are immutable
  (CLAUDE.md rule 4); a re-upload creates a new row and the previous one
  stays for the audit history. The AI extract populates ``extracted_fields``
  (JSONB) with a page ref per field; ``extract_status`` moves
  ``pending`` → ``complete`` | ``failed`` | ``manual_required``; humans then
  ``confirm`` each field and finally ``submit`` — which sets ``confirmed_by``
  and ``confirmed_at``.

Portable JSON column: JSONB on Postgres, JSON on SQLite via the same helper
used by ``s2-e3-agreements-crud``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260918_0006"
down_revision: str | None = "20260918_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Kept in lock-step with ``app.services.sow_extract.ALLOWED_EXTRACT_STATUSES``.
_EXTRACT_STATUSES: tuple[str, ...] = (
    "pending",
    "complete",
    "failed",
    "manual_required",
)


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def _status_check_expr() -> str:
    quoted = ", ".join(f"'{s}'" for s in _EXTRACT_STATUSES)
    return f"extract_status IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "sow",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "opportunity_id",
            sa.Uuid(),
            sa.ForeignKey("opportunity.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "sow_version",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "sow_id",
            sa.Uuid(),
            sa.ForeignKey("sow.id"),
            nullable=False,
        ),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("file_s3_key", sa.String(length=1024), nullable=False),
        sa.Column("file_hash", sa.String(length=128), nullable=False),
        # Nullable until the extract job runs.
        sa.Column("extracted_fields", _json_type(), nullable=True),
        sa.Column(
            "extract_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("extract_model", sa.String(length=128), nullable=True),
        sa.Column("extract_prompt_version", sa.String(length=32), nullable=True),
        sa.Column("confirmed_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("engagement_type_suggested", sa.String(length=64), nullable=True),
        sa.Column("engagement_type_confirmed", sa.String(length=64), nullable=True),
        sa.CheckConstraint(_status_check_expr(), name="ck_sow_version_extract_status"),
    )
    op.create_index(
        "ix_sow_version_sow_uploaded_at",
        "sow_version",
        ["sow_id", "uploaded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sow_version_sow_uploaded_at", table_name="sow_version")
    op.drop_table("sow_version")
    op.drop_table("sow")
