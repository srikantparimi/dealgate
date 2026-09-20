"""SOW version lifecycle: numbering, supersede, discard (S10-06).

Before this, the versioning table existed but nothing reached it from the
SOW-first flow. Uploading a corrected SOW either created a second
opportunity for the same engagement (when the business-key dedupe could not
fire because the term dates were missing) or was refused outright as a
duplicate. Neither produced "version 2", and there was no way at all to get
rid of a bad upload — the API had no delete route for a SOW, a version, an
upload job or an opportunity.

Adds:

- ``version_no``      — per-Sow ordinal starting at 1.
- ``version_counter`` — on ``sow``. MAX(version_no) is not enough: delete the
                        highest version and MAX drops, so the next upload
                        reuses that number and the audit trail ends up with
                        two different documents recorded as "version 2".
- ``superseded_by`` — set on the older version when a revision replaces it,
                      so the chain is explicit rather than inferred from
                      timestamps.
- ``discarded_*``   — soft discard for a version that has already been
                      through approval and so cannot be deleted
                      (CLAUDE.md rule 4).

``execution_state`` and ``governance_status`` already exist from 0029; this
migration does not touch them. It backfills ``version_no`` in upload order
per Sow so existing rows are numbered sensibly.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260922_0030"
down_revision: str | Sequence[str] | None = "20260921_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("sow", "version_counter"):
        with op.batch_alter_table("sow") as batch:
            batch.add_column(
                sa.Column(
                    "version_counter",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )

    with op.batch_alter_table("sow_version") as batch:
        if not _column_exists("sow_version", "version_no"):
            batch.add_column(
                sa.Column(
                    "version_no",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("1"),
                )
            )
        if not _column_exists("sow_version", "superseded_by"):
            batch.add_column(sa.Column("superseded_by", sa.Uuid(), nullable=True))
        if not _column_exists("sow_version", "discarded_at"):
            batch.add_column(
                sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True)
            )
        if not _column_exists("sow_version", "discarded_by"):
            batch.add_column(sa.Column("discarded_by", sa.Uuid(), nullable=True))
        if not _column_exists("sow_version", "discard_reason"):
            batch.add_column(
                sa.Column("discard_reason", sa.String(length=500), nullable=True)
            )

    # Number existing rows per Sow in upload order. Postgres only — the
    # SQLite test path starts from an empty database, so there is nothing to
    # backfill there and the window function is not worth emulating.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE sow_version AS sv
                SET version_no = ordered.rn
                FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY sow_id
                               ORDER BY uploaded_at ASC, id ASC
                           ) AS rn
                    FROM sow_version
                ) AS ordered
                WHERE sv.id = ordered.id
                """
            )
        )
        # Deliberately NOT adding a "one current version per SOW" unique
        # index. Creating v2 means inserting it and then pointing v1 at it,
        # and between those two statements both rows are non-superseded.
        # Postgres evaluates unique indexes at statement end, so such an
        # index would reject the very operation it exists to describe.
        # "One current version" is enforced in the service layer instead.

    op.create_index(
        "ix_sow_version_sow_id_version_no",
        "sow_version",
        ["sow_id", "version_no"],
        unique=True,
    )


def downgrade() -> None:
    if _column_exists("sow", "version_counter"):
        with op.batch_alter_table("sow") as batch:
            batch.drop_column("version_counter")
    op.drop_index("ix_sow_version_sow_id_version_no", table_name="sow_version")
    with op.batch_alter_table("sow_version") as batch:
        for col in (
            "discard_reason",
            "discarded_by",
            "discarded_at",
            "superseded_by",
            "version_no",
        ):
            if _column_exists("sow_version", col):
                batch.drop_column(col)
