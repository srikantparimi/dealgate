"""S24-AG1 — NDA & MSA: standard copies, marks, the one-time batch, relationship, msa_type.

* ``standard_agreement``: each version of the standard NDA/MSA (one stored object each).
* ``agreement``: ``source`` (client | standard), ``standard_agreement_id``, ``batch_id``, ``note``;
  one agreement per client and kind (the old non-unique index becomes unique).
* ``agreement_file_version``: the same provenance per version, for history.
* ``agreement_mark``: a kind marked covered with no file (one active mark per client and kind).
* ``agreement_batch``: the resumable attach job with undo; ``running_guard`` allows one at a time.
* ``agreements_settings``: singleton row holding the cutover date.
* ``agreement_hubspot_map``: which HubSpot ``msa_type`` values mean "MSA covered".
* ``client``: relationship (existing | net_new), basis, who and when.
* ``opportunity``: raw HubSpot ``msa_type``.

Existing agreement rows are client copies, so they get ``source='client'``. The downgrade refuses
once any AG1 evidence exists (a standard copy, an attachment, a mark, a batch, the cutover, a
stamped relationship or a saved HubSpot mapping), like 0063 does for revision history.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Alembic's version_num column is VARCHAR(32); keep revision <= 32 chars.
revision = "20261015_0072_agreements_ag1"
down_revision = "20261014_0071_cognito_sub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(sa.text(
        "SELECT count(*) FROM (SELECT client_id, kind FROM agreement GROUP BY client_id, kind HAVING count(*) > 1) d"
    )).scalar()
    if duplicates:
        raise RuntimeError(
            f"{duplicates} client/kind pairs hold more than one agreement row; resolve them before AG1 makes the pair unique"
        )

    op.create_table(
        "standard_agreement",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("file_key", sa.String(1024), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('NDA', 'MSA')", name="ck_standard_agreement_kind"),
        sa.CheckConstraint("version_no > 0", name="ck_standard_agreement_version"),
        sa.UniqueConstraint("kind", "version_no", name="uq_standard_agreement_kind_version"),
    )
    op.create_table(
        "agreement_batch",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("label", sa.String(16), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("kinds", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("include_net_new", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("target_client_ids", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
                  nullable=False),
        sa.Column("standard_ids", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
                  nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("done_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attached_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attached_clients", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("undone_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(1024), nullable=True),
        sa.Column("idempotency_key", sa.String(80), nullable=False, unique=True),
        sa.Column("running_guard", sa.Boolean(), nullable=True, unique=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint("status IN ('running', 'done', 'failed', 'undoing', 'undone')",
                           name="ck_agreement_batch_status"),
        sa.CheckConstraint("running_guard IS NULL OR running_guard", name="ck_agreement_batch_guard"),
        sa.CheckConstraint(
            "target_count >= 0 AND done_count >= 0 AND attached_count >= 0 AND skipped_count >= 0 "
            "AND attached_clients >= 0 AND undone_count >= 0",
            name="ck_agreement_batch_counts",
        ),
    )
    op.create_table(
        "agreement_mark",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("marked_on", sa.Date(), nullable=False),
        sa.Column("marked_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="dealgate"),
        sa.Column("hubspot_value", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint("kind IN ('NDA', 'MSA')", name="ck_agreement_mark_kind"),
        sa.CheckConstraint(
            "reason IN ('signed_outside_dealgate', 'covered_by_earlier_work', 'confirmed_with_client', "
            "'per_hubspot', 'other')",
            name="ck_agreement_mark_reason",
        ),
        sa.CheckConstraint("source IN ('dealgate', 'hubspot')", name="ck_agreement_mark_source"),
    )
    op.create_index(
        "ux_agreement_mark_active", "agreement_mark", ["client_id", "kind"], unique=True,
        postgresql_where=sa.text("removed_at IS NULL"), sqlite_where=sa.text("removed_at IS NULL"),
    )
    op.create_table(
        "agreements_settings",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("cutover_date", sa.Date(), nullable=True),
        sa.Column("set_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_agreements_settings_singleton"),
    )
    op.execute("INSERT INTO agreements_settings (id) VALUES (1)")
    op.create_table(
        "agreement_hubspot_map",
        sa.Column("value", sa.String(200), primary_key=True),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("action IN ('covered', 'ignore')", name="ck_agreement_hubspot_map_action"),
    )

    with op.batch_alter_table("agreement") as batch:
        batch.add_column(sa.Column("source", sa.String(16), nullable=False, server_default="client"))
        batch.add_column(sa.Column("standard_agreement_id", sa.Uuid(),
                                   sa.ForeignKey("standard_agreement.id", name="fk_agreement_standard_agreement"),
                                   nullable=True))
        batch.add_column(sa.Column("batch_id", sa.Uuid(),
                                   sa.ForeignKey("agreement_batch.id", name="fk_agreement_batch"), nullable=True))
        batch.add_column(sa.Column("note", sa.String(200), nullable=True))
        batch.create_check_constraint("ck_agreement_source", "source IN ('client', 'standard')")
        batch.create_check_constraint("ck_agreement_standard_ref",
                                      "source = 'client' OR standard_agreement_id IS NOT NULL")
        batch.drop_index("ix_agreement_client_kind")
        batch.create_index("ux_agreement_client_kind", ["client_id", "kind"], unique=True)

    with op.batch_alter_table("agreement_file_version") as batch:
        batch.add_column(sa.Column("source", sa.String(16), nullable=True))
        batch.add_column(sa.Column("standard_agreement_id", sa.Uuid(),
                                   sa.ForeignKey("standard_agreement.id", name="fk_agreement_file_version_standard"),
                                   nullable=True))
        batch.add_column(sa.Column("batch_id", sa.Uuid(),
                                   sa.ForeignKey("agreement_batch.id", name="fk_agreement_file_version_batch"),
                                   nullable=True))
        batch.add_column(sa.Column("note", sa.String(200), nullable=True))
        batch.create_check_constraint("ck_agreement_file_version_source",
                                      "source IS NULL OR source IN ('client', 'standard')")

    with op.batch_alter_table("client") as batch:
        batch.add_column(sa.Column("relationship", sa.String(16), nullable=True))
        batch.add_column(sa.Column("relationship_basis", sa.String(32), nullable=True))
        batch.add_column(sa.Column("relationship_set_by", sa.Uuid(),
                                   sa.ForeignKey("user.id", name="fk_client_relationship_set_by"), nullable=True))
        batch.add_column(sa.Column("relationship_set_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint("ck_client_relationship",
                                      "relationship IS NULL OR relationship IN ('existing', 'net_new')")
        batch.create_check_constraint(
            "ck_client_relationship_basis",
            "relationship_basis IS NULL OR relationship_basis IN "
            "('closed_won', 'sow_engagement', 'closed_won_and_sow', 'manual', 'none')",
        )

    with op.batch_alter_table("opportunity") as batch:
        batch.add_column(sa.Column("hubspot_msa_type", sa.String(200), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    evidence = bind.execute(sa.text(
        "SELECT (SELECT count(*) FROM standard_agreement) + (SELECT count(*) FROM agreement_batch) "
        "+ (SELECT count(*) FROM agreement_mark) + (SELECT count(*) FROM agreement WHERE source <> 'client') "
        "+ (SELECT count(*) FROM agreement_file_version WHERE source IS NOT NULL OR note IS NOT NULL) "
        "+ (SELECT count(*) FROM agreements_settings WHERE cutover_date IS NOT NULL) "
        "+ (SELECT count(*) FROM client WHERE relationship IS NOT NULL)"
        "+ (SELECT count(*) FROM agreement_hubspot_map)"
    )).scalar()
    if evidence:
        raise RuntimeError("AG1 agreement evidence exists; downgrade would discard standard copies, marks, batches, "
                           "the cutover, stamped relationships or the saved HubSpot msa_type mapping")

    with op.batch_alter_table("opportunity") as batch:
        batch.drop_column("hubspot_msa_type")
    with op.batch_alter_table("client") as batch:
        batch.drop_constraint("ck_client_relationship_basis", type_="check")
        batch.drop_constraint("ck_client_relationship", type_="check")
        batch.drop_column("relationship_set_at")
        batch.drop_column("relationship_set_by")
        batch.drop_column("relationship_basis")
        batch.drop_column("relationship")
    with op.batch_alter_table("agreement_file_version") as batch:
        batch.drop_constraint("ck_agreement_file_version_source", type_="check")
        batch.drop_column("note")
        batch.drop_column("batch_id")
        batch.drop_column("standard_agreement_id")
        batch.drop_column("source")
    with op.batch_alter_table("agreement") as batch:
        batch.drop_index("ux_agreement_client_kind")
        batch.create_index("ix_agreement_client_kind", ["client_id", "kind"])
        batch.drop_constraint("ck_agreement_standard_ref", type_="check")
        batch.drop_constraint("ck_agreement_source", type_="check")
        batch.drop_column("note")
        batch.drop_column("batch_id")
        batch.drop_column("standard_agreement_id")
        batch.drop_column("source")
    op.drop_table("agreement_hubspot_map")
    op.drop_table("agreements_settings")
    op.drop_index("ux_agreement_mark_active", table_name="agreement_mark")
    op.drop_table("agreement_mark")
    op.drop_table("agreement_batch")
    op.drop_table("standard_agreement")
