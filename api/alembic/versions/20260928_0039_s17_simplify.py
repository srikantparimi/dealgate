"""S17 simplify: agreements become a flat doc store, drop tracking + gap tables.

Contract shifts:
- ``agreement`` shrinks to (id, client_id, kind, file_key, filename,
  file_size, uploaded_by, uploaded_at). State machine, owner_email,
  next_action, dates, signatories, evidence_s3_key, legal_entity_id all
  go — the file is the truth now.
- ``agreement_gap`` (S16a's obtain-signed-doc task registry) is deleted.
- ``agreement_document`` (S16a's extract-once evidence store) is deleted.
- ``sow_version`` gets ``agreements_signed BOOLEAN NOT NULL DEFAULT FALSE`` —
  the SOW-upload checkbox writes here; UI shows it as a note; no gates
  read it.

Data policy per the S17 directive §3: staging is being wiped in the same
slice, so historical agreement rows are not preserved. The upgrade drops
the old columns unconditionally; the downgrade re-adds them empty.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260928_0039_s17_simplify"
down_revision = "20260926_0038_merge_s14b_s16a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_table("agreement_document")
    op.drop_table("agreement_gap")

    # Recreate `agreement` from scratch so both SQLite and Postgres end up
    # with the same shape and we don't have to write per-dialect ALTERs
    # for the many column drops.
    op.drop_table("agreement")
    op.create_table(
        "agreement",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("file_key", sa.String(1024), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('NDA', 'MSA')", name="ck_agreement_kind"),
    )
    op.create_index("ix_agreement_client_kind", "agreement", ["client_id", "kind"])

    if dialect == "sqlite":
        with op.batch_alter_table("sow_version") as batch:
            batch.add_column(
                sa.Column(
                    "agreements_signed",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )
    else:
        op.add_column(
            "sow_version",
            sa.Column(
                "agreements_signed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("sow_version") as batch:
            batch.drop_column("agreements_signed")
    else:
        op.drop_column("sow_version", "agreements_signed")

    op.drop_index("ix_agreement_client_kind", table_name="agreement")
    op.drop_table("agreement")

    # Re-create the S16a shape (empty) so a downgrade leaves valid tables.
    op.create_table(
        "agreement",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("legal_entity_id", sa.Uuid(), sa.ForeignKey("legal_entity.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="missing"),
        sa.Column("owner_email", sa.String(320)),
        sa.Column("next_action", sa.String(255)),
        sa.Column("due_date", sa.Date()),
        sa.Column("effective_from", sa.Date()),
        sa.Column("effective_date", sa.Date()),
        sa.Column("expiry", sa.Date()),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("notice_days", sa.Integer()),
        sa.Column("evidence_s3_key", sa.String(1024)),
        sa.Column("signatories", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "agreement_gap",
        sa.Column(
            "legal_entity_id", sa.Uuid(), sa.ForeignKey("legal_entity.id"), primary_key=True
        ),
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("task.id"), nullable=False),
    )
    op.create_table(
        "agreement_document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agreement_id", sa.Uuid(), sa.ForeignKey("agreement.id"), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("file_s3_key", sa.String(1024), nullable=False),
        sa.Column("extracted_fields", sa.JSON(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
    )
