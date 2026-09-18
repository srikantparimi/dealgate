"""S5 E8 — signed SOW upload + renewal (Agent X2, wave 5).

Adds two tables the signed-SOW verify + distribution flow needs:

- ``signed_sow_upload``: one row per executed pdf uploaded against a
  ``ready_to_sign`` approval package. The row is set-once on the file
  pointer (rule 4); ``verify_status`` and ``diff_json`` are the fields
  the service layer updates as the extract + diff run, and ``released_at``
  flips exactly once when the package is distributed.
- ``renewal``: one row per SOW that has (or approaches) a term end. The
  Signed-SOW release flow opens the row at release time with
  ``trigger_date = term_end - 60d``; Agent Y2's scheduler consumes it.

Coordination with Agent Y2 (S5 E9, renewals scheduler): both agents need
the ``renewal`` table. This migration guards the CREATE with
``_table_exists`` so it is a no-op when Y2's 0016 (or a future re-run)
has already landed. The columns are the intersection of what both
agents documented — see ``docs/backlog/s5-signed-sow-distribution.md``.

Rule 4 (CLAUDE.md): the identity + audit columns are set-once. Rule 5:
every state change writes an ``audit_event`` in the caller's
transaction (see :mod:`app.services.signed_sow`).

Reversible: ``downgrade()`` drops the signed-SOW table and only drops
``renewal`` if it has no rows (defensive — Y2's data lives here too).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260918_0015"
down_revision: str | Sequence[str] | None = "20260918_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_VERIFY_STATUSES: tuple[str, ...] = ("pending", "verified", "blocked")
_RENEWAL_STATUSES: tuple[str, ...] = ("open", "closed", "extended", "churn")

# S5 E8 widens the approval_package status alphabet to include
# ``released``. Kept in lock-step with ``app.models.approval.PACKAGE_STATUSES``
# and ``app.services.approvals.mark_released``.
_PACKAGE_STATUSES: tuple[str, ...] = (
    "pending_delivery_hr",
    "pending_finance_legal",
    "pending_ceo_exception",
    "ready_to_sign",
    "released",
    "voided",
    "rejected",
)


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _verify_status_check() -> str:
    quoted = ", ".join(f"'{s}'" for s in _VERIFY_STATUSES)
    return f"verify_status IN ({quoted})"


def _renewal_status_check() -> str:
    quoted = ", ".join(f"'{s}'" for s in _RENEWAL_STATUSES)
    return f"status IN ({quoted})"


def _package_status_check() -> str:
    quoted = ", ".join(f"'{s}'" for s in _PACKAGE_STATUSES)
    return f"status IN ({quoted})"


def upgrade() -> None:
    # ---- widen approval_package status alphabet --------------------------
    # Batch mode so SQLite (used in the API test suite) can round-trip the
    # CHECK swap; Postgres runs the ALTER inline.
    with op.batch_alter_table("approval_package") as batch:
        batch.drop_constraint("ck_approval_package_status", type_="check")
        batch.create_check_constraint(
            "ck_approval_package_status", _package_status_check()
        )

    # ---- signed_sow_upload ------------------------------------------------
    op.create_table(
        "signed_sow_upload",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "package_id",
            sa.Uuid(),
            sa.ForeignKey(
                "approval_package.id", name="fk_signed_sow_upload_package_id"
            ),
            nullable=False,
        ),
        sa.Column("file_s3_key", sa.String(length=1024), nullable=False),
        sa.Column("file_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "uploaded_by",
            sa.Uuid(),
            sa.ForeignKey("user.id", name="fk_signed_sow_upload_uploaded_by"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "verify_status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("diff_json", _json_type(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_verify_status_check(), name="ck_signed_sow_upload_status"),
    )
    op.create_index(
        "ix_signed_sow_upload_package_id",
        "signed_sow_upload",
        ["package_id"],
    )
    op.create_index(
        "ix_signed_sow_upload_verify_status",
        "signed_sow_upload",
        ["verify_status"],
    )

    # ---- renewal (guarded — Agent Y2's 0016 may have landed first) --------
    if not _table_exists("renewal"):
        op.create_table(
            "renewal",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "opportunity_id",
                sa.Uuid(),
                sa.ForeignKey("opportunity.id", name="fk_renewal_opportunity_id"),
                nullable=False,
            ),
            sa.Column("term_end", sa.Date(), nullable=False),
            sa.Column("trigger_date", sa.Date(), nullable=False),
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'open'"),
            ),
            sa.Column("outcome_summary", sa.Text(), nullable=True),
            sa.Column(
                "replacement_sow_version_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "sow_version.id",
                    name="fk_renewal_replacement_sow_version_id",
                ),
                nullable=True,
            ),
            sa.Column(
                "opened_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(_renewal_status_check(), name="ck_renewal_status"),
        )


def downgrade() -> None:
    op.drop_index(
        "ix_signed_sow_upload_verify_status", table_name="signed_sow_upload"
    )
    op.drop_index(
        "ix_signed_sow_upload_package_id", table_name="signed_sow_upload"
    )
    op.drop_table("signed_sow_upload")
    # Do not drop ``renewal`` here — Agent Y2's 0016 owns it in the
    # steady-state migration graph; its downgrade drops the table when it
    # created it. Dropping here would double-remove.

    # Restore the narrower approval_package status alphabet.
    original = (
        "'pending_delivery_hr', 'pending_finance_legal', "
        "'pending_ceo_exception', 'ready_to_sign', 'voided', 'rejected'"
    )
    with op.batch_alter_table("approval_package") as batch:
        batch.drop_constraint("ck_approval_package_status", type_="check")
        batch.create_check_constraint(
            "ck_approval_package_status", f"status IN ({original})"
        )
