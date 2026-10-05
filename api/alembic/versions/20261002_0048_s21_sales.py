"""Add Sales reviews without reinterpreting historical approval packages."""

import sqlalchemy as sa
from alembic import op

revision = "20261002_0048_s21_sales"
down_revision = "20260930_0047_w6_watch"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("approval_package", sa.Column("routing_policy_version", sa.Integer(),
                                               server_default="1", nullable=False))
    with op.batch_alter_table("approval_package") as batch:
        batch.create_check_constraint("ck_approval_routing_policy_version", "routing_policy_version IN (1, 2)")
    for table, name in (("approval", "ck_approval_function"),
                        ("function_owner", "ck_function_owner_function")):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="check")
            batch.create_check_constraint(name, "function IN ('delivery','hr','sales','finance','legal')")


def downgrade():
    connection = op.get_bind()
    for table in ("approval", "function_owner"):
        if connection.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE function = 'sales'")):
            raise RuntimeError("Cannot remove Sales schema with recorded Sales reviews/owners")
    if connection.scalar(sa.text("SELECT count(*) FROM approval_package WHERE routing_policy_version = 2")):
        raise RuntimeError("Cannot remove frozen S21 routing policy from existing packages")
    for table, name in (("approval", "ck_approval_function"),
                        ("function_owner", "ck_function_owner_function")):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="check")
            batch.create_check_constraint(name, "function IN ('delivery','hr','finance','legal')")
    with op.batch_alter_table("approval_package") as batch:
        batch.drop_constraint("ck_approval_routing_policy_version", type_="check")
        batch.drop_column("routing_policy_version")
