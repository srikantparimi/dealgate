"""CRM owner and Business Unit observations without invented backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261002_0054_source_facts"
down_revision = "20261002_0053_parent_deletion"
branch_labels = None
depends_on = None

SOURCE_FIELDS = (
    ("hubspot_owner_id", sa.String(64)),
    ("hubspot_owner_observed_at", sa.DateTime(timezone=True)),
    ("business_unit_value", sa.String(255)),
    ("business_unit_mapping_version", sa.Integer()),
    ("business_unit_observed_at", sa.DateTime(timezone=True)),
)
CLIENT_FIELDS = (
    ("hubspot_last_modified_at", sa.DateTime(timezone=True)),
    ("hubspot_last_seen_at", sa.DateTime(timezone=True)),
)
IDENTITY_FIELDS = (("internal_name", sa.String(128)), ("object_type", sa.String(32)),
    ("label", sa.String(255)), ("field_type", sa.String(32)))


def upgrade():
    for table in ("client", "opportunity"):
        for name, datatype in SOURCE_FIELDS:
            op.add_column(table, sa.Column(name, datatype, nullable=True))
        op.create_index(f"ix_{table}_hubspot_owner_id", table, ["hubspot_owner_id"])
        op.create_check_constraint(f"ck_{table}_bu_version", table,
            "business_unit_mapping_version IS NULL OR business_unit_mapping_version > 0")
    for name, datatype in CLIENT_FIELDS:
        op.add_column("client", sa.Column(name, datatype, nullable=True))
    op.add_column("opportunity", sa.Column("local_assignee_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_opportunity_local_assignee", "opportunity", "user",
        ["local_assignee_id"], ["id"], ondelete="SET NULL")
    table = "hubspot_property_mapping"
    for name, datatype in IDENTITY_FIELDS:
        op.alter_column(table, name, existing_type=datatype, nullable=True)
    op.add_column(table, sa.Column("availability_state", sa.String(16), nullable=False, server_default="unknown"))
    op.add_column(table, sa.Column("availability_reason", sa.String(1024)))
    op.add_column(table, sa.Column("checked_at", sa.DateTime(timezone=True)))
    op.add_column(table, sa.Column("last_success_at", sa.DateTime(timezone=True)))
    op.add_column(table, sa.Column("mapping_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(table, sa.Column("evidence", sa.JSON().with_variant(postgresql.JSONB(), "postgresql")))
    op.add_column(table, sa.Column("selected_by", sa.Uuid()))
    op.create_foreign_key("fk_hubspot_mapping_selected_by", table, "user", ["selected_by"], ["id"])
    op.create_check_constraint("ck_hubspot_mapping_version", table, "mapping_version > 0")
    op.create_check_constraint("ck_hubspot_mapping_availability", table,
        "availability_state IN ('unknown','configured','absent','ambiguous','unavailable')")


def downgrade():
    bind = op.get_bind()
    # Refuse a lossy downgrade; rolling application code back keeps the expanded schema.
    for table in ("client", "opportunity"):
        fields = [name for name, _ in SOURCE_FIELDS]
        fields += [name for name, _ in CLIENT_FIELDS] if table == "client" else ["local_assignee_id"]
        predicate = " OR ".join(f"{name} IS NOT NULL" for name in fields)
        if bind.execute(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {predicate})")).scalar():
            raise RuntimeError("Cannot discard CRM source observations or local assignments")
    table = "hubspot_property_mapping"
    if bind.execute(sa.text("SELECT EXISTS(SELECT 1 FROM hubspot_property_mapping WHERE "
        "availability_state <> 'unknown' OR mapping_version <> 1 OR availability_reason IS NOT NULL "
        "OR checked_at IS NOT NULL OR last_success_at IS NOT NULL OR evidence IS NOT NULL OR selected_by IS NOT NULL "
        "OR internal_name IS NULL OR object_type IS NULL OR label IS NULL OR field_type IS NULL)")).scalar():
        raise RuntimeError("Cannot discard CRM mapping evidence or restore invalid legacy identity")
    op.drop_constraint("ck_hubspot_mapping_availability", table, type_="check")
    op.drop_constraint("ck_hubspot_mapping_version", table, type_="check")
    op.drop_constraint("fk_hubspot_mapping_selected_by", table, type_="foreignkey")
    for name in ("selected_by", "evidence", "mapping_version", "last_success_at", "checked_at", "availability_reason", "availability_state"):
        op.drop_column(table, name)
    for name, datatype in IDENTITY_FIELDS:
        op.alter_column(table, name, existing_type=datatype, nullable=False)
    op.drop_constraint("fk_opportunity_local_assignee", "opportunity", type_="foreignkey")
    op.drop_column("opportunity", "local_assignee_id")
    for name, _ in reversed(CLIENT_FIELDS):
        op.drop_column("client", name)
    for table in ("client", "opportunity"):
        op.drop_constraint(f"ck_{table}_bu_version", table, type_="check")
        op.drop_index(f"ix_{table}_hubspot_owner_id", table_name=table)
        for name, _ in reversed(SOURCE_FIELDS):
            op.drop_column(table, name)
