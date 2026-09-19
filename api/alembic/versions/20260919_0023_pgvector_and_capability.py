"""S7 wave 2 — pgvector + capability catalog + adviser retrieved.

Revision ID: 20260919_0023
Revises: 20260919_0021
Create Date: 2026-09-19

Adds:

- ``CREATE EXTENSION IF NOT EXISTS vector`` (Postgres only). SQLite skips
  the extension and stores the ``embedding`` column as JSON (see
  :mod:`app.db.vector`).
- ``sow_embedding``: one row per ~500-char chunk of a confirmed SOW's
  scope + deliverables. Unique on ``(sow_version_id, chunk_index)`` so
  re-embed jobs are idempotent. On Postgres we index the embedding with
  HNSW / ``vector_cosine_ops``; on SQLite we skip the index.
- ``capability_catalog``: curated capability entries with an embedding
  used for adviser retrieval.
- ``adviser_estimate.retrieved`` JSONB — snapshot of the past-SOW and
  capability refs the LLM saw for a given estimate.

Every DDL branch is guarded on ``dialect.name`` so the same migration
runs against SQLite (tests, local dev) and Postgres (staging, prod).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260919_0023"
# Chains directly on top of Agent GG's ``0022_adviser_research`` so the new
# ``retrieved`` JSONB column lands in the same lineage as
# ``research_status``. Agent JJ's ``0024_wbs_and_templates`` also parents
# ``0021`` — the merge migration ``0025`` reconciles the three heads.
down_revision: str | Sequence[str] | None = "20260919_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_EMBEDDING_DIM = 1536


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _json_type() -> sa.types.TypeEngine:
    return JSONB() if _is_postgres() else sa.JSON()


def _embedding_column() -> sa.Column:
    """Portable embedding column: VECTOR(1536) on PG, JSON string on SQLite.

    The SQLite branch stores a JSON-encoded list of floats; the service
    layer decodes on read and falls back to a Python dot-product for
    similarity when pgvector isn't available.
    """

    if _is_postgres():
        # Emit the raw pgvector type via ``type_`` = a bare TypeEngine.
        # Cannot use ``sa.dialects.postgresql`` here because pgvector's
        # SQL name isn't in stock SQLAlchemy — text() the DDL fragment.
        return sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float()), nullable=True)  # noqa: E501
    return sa.Column("embedding", sa.JSON(), nullable=True)


def upgrade() -> None:
    postgres = _is_postgres()

    if postgres:
        # Guarded — no-op if the extension is already installed. Requires
        # the app role to be a member of ``rds_superuser`` on RDS. If the
        # deploy role can't create extensions, the DBA must run this once
        # by hand and this line becomes a no-op.
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- sow_embedding -----------------------------------------------------
    op.create_table(
        "sow_embedding",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "sow_version_id",
            sa.Uuid(),
            sa.ForeignKey("sow_version.id"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        _embedding_column(),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "sow_version_id",
            "chunk_index",
            name="uq_sow_embedding_version_chunk",
        ),
    )
    op.create_index(
        "ix_sow_embedding_version",
        "sow_embedding",
        ["sow_version_id"],
    )

    if postgres:
        # Swap the placeholder ARRAY(Float) type for the real VECTOR(1536)
        # so pgvector operators bind. ARRAY(Float) is stored the same way
        # on disk for a fresh table but the operator class needs VECTOR.
        op.execute(
            f"ALTER TABLE sow_embedding "
            f"ALTER COLUMN embedding TYPE VECTOR({_EMBEDDING_DIM}) "
            f"USING embedding::text::vector"
        )
        op.execute(
            "CREATE INDEX ix_sow_embedding_hnsw ON sow_embedding "
            "USING hnsw (embedding vector_cosine_ops)"
        )

    # --- capability_catalog ------------------------------------------------
    op.create_table(
        "capability_catalog",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            sa.dialects.postgresql.ARRAY(sa.String()) if postgres else sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'") if postgres else sa.text("'[]'"),
        ),
        _embedding_column(),
        sa.Column(
            "curated_by",
            sa.Uuid(),
            sa.ForeignKey("user.id"),
            nullable=True,
        ),
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
    )
    op.create_index(
        "ix_capability_catalog_name",
        "capability_catalog",
        ["name"],
    )

    if postgres:
        op.execute(
            f"ALTER TABLE capability_catalog "
            f"ALTER COLUMN embedding TYPE VECTOR({_EMBEDDING_DIM}) "
            f"USING embedding::text::vector"
        )
        # HNSW requires a non-null embedding — leaving nullable rows out of
        # the index keeps the ANN index compact until curators embed them.
        op.execute(
            "CREATE INDEX ix_capability_catalog_hnsw ON capability_catalog "
            "USING hnsw (embedding vector_cosine_ops) "
            "WHERE embedding IS NOT NULL"
        )

    # --- adviser_estimate.retrieved ---------------------------------------
    with op.batch_alter_table("adviser_estimate") as batch:
        batch.add_column(sa.Column("retrieved", _json_type(), nullable=True))


def downgrade() -> None:
    postgres = _is_postgres()

    with op.batch_alter_table("adviser_estimate") as batch:
        batch.drop_column("retrieved")

    if postgres:
        op.execute("DROP INDEX IF EXISTS ix_capability_catalog_hnsw")
    op.drop_index("ix_capability_catalog_name", table_name="capability_catalog")
    op.drop_table("capability_catalog")

    if postgres:
        op.execute("DROP INDEX IF EXISTS ix_sow_embedding_hnsw")
    op.drop_index("ix_sow_embedding_version", table_name="sow_embedding")
    op.drop_table("sow_embedding")

    # Deliberately do not drop the extension — other features may depend
    # on pgvector after this migration lands.
