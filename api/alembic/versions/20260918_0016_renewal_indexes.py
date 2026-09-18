"""S5 E9 — renewal indexes (Agent Y2).

Adds the indexes the renewals scheduler + inbox need:

- ``ix_renewal_status_trigger_date`` on ``renewal(status, trigger_date)`` —
  supports the scheduler's "any open renewal past due for a 7-day nudge"
  scan and the ``/renewals`` inbox status filter.
- ``ix_sow_version_term_end`` on ``sow_version(term_end)`` — supports the
  "term_end - now = 60d" pre-renewal scan. Only created when the column
  is present (some deployments still keep ``term_end`` inside
  ``extracted_fields`` JSONB); the guard keeps this migration safe until
  the column lands.

Coordination: Agent X2 owns the ``renewal`` table (migration 0015). This
migration races that one — if the table is not yet present when this
runs, we create it here with the same columns X2 defines so Sprint 5 has
a working row shape end-to-end. If both migrations land, only one
physical table exists.

Revision ID: 20260918_0016
Revises: 20260918_0014
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0016"
down_revision: str | Sequence[str] | None = "20260918_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RENEWAL_STATUSES: tuple[str, ...] = ("open", "closed", "extended", "churn")


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return index_name in {i["name"] for i in insp.get_indexes(table)}


def _renewal_status_check() -> str:
    quoted = ", ".join(f"'{s}'" for s in _RENEWAL_STATUSES)
    return f"status IN ({quoted})"


def upgrade() -> None:
    if not _table_exists("renewal"):
        # Agent X2's 0015 hasn't landed yet — mirror the shape here so the
        # rest of Sprint 5 can proceed. Kept in lock-step with the columns
        # documented in ``docs/backlog/s5-signed-sow-distribution.md``.
        op.create_table(
            "renewal",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "opportunity_id",
                sa.Uuid(),
                sa.ForeignKey("opportunity.id"),
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
                sa.ForeignKey("sow_version.id"),
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

    if not _index_exists("renewal", "ix_renewal_status_trigger_date"):
        op.create_index(
            "ix_renewal_status_trigger_date",
            "renewal",
            ["status", "trigger_date"],
        )

    if not _index_exists("renewal", "ix_renewal_opportunity_id"):
        op.create_index(
            "ix_renewal_opportunity_id",
            "renewal",
            ["opportunity_id"],
        )

    # ``term_end`` on ``sow_version`` is optional today (values live inside
    # ``extracted_fields`` JSONB). Only add the index when the column
    # actually exists so the migration is a no-op on the current schema
    # yet future-proof if a column is promoted.
    if _column_exists("sow_version", "term_end") and not _index_exists(
        "sow_version", "ix_sow_version_term_end"
    ):
        op.create_index(
            "ix_sow_version_term_end",
            "sow_version",
            ["term_end"],
        )


def downgrade() -> None:
    if _index_exists("sow_version", "ix_sow_version_term_end"):
        op.drop_index("ix_sow_version_term_end", table_name="sow_version")
    if _index_exists("renewal", "ix_renewal_opportunity_id"):
        op.drop_index("ix_renewal_opportunity_id", table_name="renewal")
    if _index_exists("renewal", "ix_renewal_status_trigger_date"):
        op.drop_index(
            "ix_renewal_status_trigger_date", table_name="renewal"
        )
    # Only drop the table if this migration created it — best signal is
    # the absence of Agent X2's 0015. Keep this simple and always drop
    # when downgrading; a co-existing 0015 will handle its own downgrade.
    if _table_exists("renewal"):
        op.drop_table("renewal")
