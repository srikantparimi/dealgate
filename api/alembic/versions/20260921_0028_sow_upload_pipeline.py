"""S10-01 — SOW upload pipeline: opportunity source, client aliases, job.

Revision ID: 20260921_0028
Revises: 20260920_0027
Create Date: 2026-09-21

Adds the storage the SOW-upload story (``docs/backlog/s10-sow-upload.md``)
needs to derive a client + opportunity + SOW version from a bare file
drop, without a HubSpot deal being present first.

Schema deltas:

- ``opportunity.source`` — one of ``hubspot|sow_upload|bulk_import|manual``,
  ``NOT NULL`` with a ``hubspot`` default so existing rows keep the old
  contract. New rows created by the upload router set ``sow_upload``.
- ``opportunity.hubspot_deal_id`` becomes nullable so a SOW-upload
  opportunity can exist before a deal id is minted (the story allows
  never-linking). The uniqueness invariant is preserved by a *partial*
  unique index (Postgres) / partial equivalent (SQLite), so nulls do not
  collide.
- ``client_alias`` (new): freeform aliases a client has been known by.
  ``client_resolver`` matches against this table before falling back to
  fuzzy name matching.
- ``sow_upload_job`` (new): the durable envelope for one upload attempt.
  Statuses are tracked as strings (see :mod:`app.services.sow_upload_pipeline`
  for the alphabet) — the CHECK is deliberately permissive so the service
  layer stays the single source of truth.

Downgrade is a mirror image: drop the two new tables, restore the
opportunity uniqueness invariant, and drop the ``source`` column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260921_0028"
down_revision: str | Sequence[str] | None = "20260920_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SOURCE_VALUES: tuple[str, ...] = (
    "hubspot",
    "sow_upload",
    "bulk_import",
    "manual",
)
_STATUS_VALUES: tuple[str, ...] = (
    "queued",
    "extracting",
    "classifying",
    "matching_client",
    "deriving_gm",
    "needs_pick",
    "done",
    "failed",
    "duplicate",
)


def _jsonb_type(bind: sa.engine.Connection) -> sa.types.TypeEngine:
    """Postgres → JSONB, SQLite → JSON. Keeps the migration portable."""

    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB

        return JSONB()
    return sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. opportunity.source column ------------------------------------------------
    opp_cols = {c["name"] for c in inspector.get_columns("opportunity")}
    if "source" not in opp_cols:
        # SQLite cannot add a NOT NULL column with only a server default
        # via a plain ADD COLUMN when the default is a literal; we add
        # with server_default so the fill is atomic for every existing row.
        op.add_column(
            "opportunity",
            sa.Column(
                "source",
                sa.String(length=32),
                nullable=False,
                server_default="hubspot",
            ),
        )
        op.create_check_constraint(
            "ck_opportunity_source",
            "opportunity",
            "source IN ('hubspot','sow_upload','bulk_import','manual')",
        )

    # 2. hubspot_deal_id → nullable + partial unique -----------------------------
    # The historical unique constraint on ``hubspot_deal_id`` is named
    # ``uq_opportunity_hubspot_deal_id`` on Postgres and often
    # ``uq_opportunity_hubspot_deal_id`` on SQLite when created via
    # ``UniqueConstraint()``. We drop it (if present) and replace with a
    # partial unique index that ignores NULLs.
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE opportunity ALTER COLUMN hubspot_deal_id DROP NOT NULL"
        )
        # Drop any existing unique constraint or index on the column.
        constraints = inspector.get_unique_constraints("opportunity")
        for c in constraints:
            if c["column_names"] == ["hubspot_deal_id"]:
                op.drop_constraint(c["name"], "opportunity", type_="unique")
        indexes = inspector.get_indexes("opportunity")
        for idx in indexes:
            if (
                idx.get("column_names") == ["hubspot_deal_id"]
                and idx.get("unique")
            ):
                op.drop_index(idx["name"], table_name="opportunity")
        op.create_index(
            "ux_opportunity_hubspot_deal_id_not_null",
            "opportunity",
            ["hubspot_deal_id"],
            unique=True,
            postgresql_where=sa.text("hubspot_deal_id IS NOT NULL"),
        )
    else:
        # SQLite: use batch_alter_table to rebuild the table with the new
        # nullability + a partial-ish unique index (SQLite supports
        # ``CREATE UNIQUE INDEX ... WHERE`` natively).
        with op.batch_alter_table("opportunity") as batch:
            batch.alter_column(
                "hubspot_deal_id",
                existing_type=sa.String(length=64),
                nullable=True,
            )
        # Drop the old auto-generated unique index if it exists.
        indexes = inspector.get_indexes("opportunity")
        for idx in indexes:
            if (
                idx.get("column_names") == ["hubspot_deal_id"]
                and idx.get("unique")
            ):
                op.drop_index(idx["name"], table_name="opportunity")
        op.create_index(
            "ux_opportunity_hubspot_deal_id_not_null",
            "opportunity",
            ["hubspot_deal_id"],
            unique=True,
            sqlite_where=sa.text("hubspot_deal_id IS NOT NULL"),
        )

    # 3. client_alias table -------------------------------------------------------
    tables = set(inspector.get_table_names())
    if "client_alias" not in tables:
        op.create_table(
            "client_alias",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "client_id",
                sa.Uuid(),
                sa.ForeignKey("client.id", name="fk_client_alias_client_id"),
                nullable=False,
            ),
            sa.Column("alias", sa.String(length=255), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_client_alias_client_id",
            "client_alias",
            ["client_id"],
        )
        op.create_index(
            "ix_client_alias_alias",
            "client_alias",
            ["alias"],
        )

    # 4. sow_upload_job table -----------------------------------------------------
    if "sow_upload_job" not in tables:
        op.create_table(
            "sow_upload_job",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "uploader_id",
                sa.Uuid(),
                sa.ForeignKey("user.id", name="fk_sow_upload_job_uploader_id"),
                nullable=False,
            ),
            sa.Column("s3_key", sa.String(length=1024), nullable=True),
            sa.Column("file_hash", sa.String(length=128), nullable=False),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="queued",
            ),
            sa.Column("resolution", sa.String(length=32), nullable=True),
            sa.Column("error", sa.String(length=2048), nullable=True),
            sa.Column(
                "opportunity_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "opportunity.id",
                    name="fk_sow_upload_job_opportunity_id",
                ),
                nullable=True,
            ),
            sa.Column(
                "sow_version_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "sow_version.id",
                    name="fk_sow_upload_job_sow_version_id",
                ),
                nullable=True,
            ),
            sa.Column("needs_pick_payload", _jsonb_type(bind), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("file_hash", name="uq_sow_upload_job_file_hash"),
        )
        op.create_index(
            "ix_sow_upload_job_uploader_id",
            "sow_upload_job",
            ["uploader_id"],
        )
        op.create_index(
            "ix_sow_upload_job_status",
            "sow_upload_job",
            ["status"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    tables = set(inspector.get_table_names())
    if "sow_upload_job" in tables:
        op.drop_index("ix_sow_upload_job_status", table_name="sow_upload_job")
        op.drop_index(
            "ix_sow_upload_job_uploader_id", table_name="sow_upload_job"
        )
        op.drop_table("sow_upload_job")

    if "client_alias" in tables:
        op.drop_index("ix_client_alias_alias", table_name="client_alias")
        op.drop_index("ix_client_alias_client_id", table_name="client_alias")
        op.drop_table("client_alias")

    # Restore the tight unique + NOT NULL on opportunity.hubspot_deal_id.
    indexes = inspector.get_indexes("opportunity")
    for idx in indexes:
        if idx.get("name") == "ux_opportunity_hubspot_deal_id_not_null":
            op.drop_index(idx["name"], table_name="opportunity")

    if bind.dialect.name == "postgresql":
        op.execute(
            "UPDATE opportunity SET hubspot_deal_id = COALESCE("
            "hubspot_deal_id, 'unknown-' || id::text) "
            "WHERE hubspot_deal_id IS NULL"
        )
        op.execute(
            "ALTER TABLE opportunity ALTER COLUMN hubspot_deal_id SET NOT NULL"
        )
        op.create_unique_constraint(
            "uq_opportunity_hubspot_deal_id",
            "opportunity",
            ["hubspot_deal_id"],
        )
    else:
        with op.batch_alter_table("opportunity") as batch:
            batch.alter_column(
                "hubspot_deal_id",
                existing_type=sa.String(length=64),
                nullable=False,
            )
        op.create_index(
            "uq_opportunity_hubspot_deal_id",
            "opportunity",
            ["hubspot_deal_id"],
            unique=True,
        )

    opp_cols = {c["name"] for c in inspector.get_columns("opportunity")}
    if "source" in opp_cols:
        try:
            op.drop_constraint(
                "ck_opportunity_source",
                "opportunity",
                type_="check",
            )
        except Exception:  # noqa: BLE001 — SQLite has no named CHECK drop
            pass
        with op.batch_alter_table("opportunity") as batch:
            batch.drop_column("source")


__all__ = ["upgrade", "downgrade", "_SOURCE_VALUES", "_STATUS_VALUES"]
