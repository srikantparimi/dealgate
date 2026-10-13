"""S22 P5 final, item 2 — allocation.import_key.

The forecast-model importer's identity for a row: ``to_engine``'s ``Allocation.id``
("{assignment_key}:{row_key}:{segment}"), written on import and matched on
re-import, so placeholder seats that share a name (eleven ``TBC`` rows) survive a
second import. Nullable (rows the app creates have none); unique per engagement
where set. Reversible.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261013_0067_import_key"
down_revision = "20261012_0066_bu_actuals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("allocation") as batch:
        batch.add_column(sa.Column("import_key", sa.Text(), nullable=True))
        batch.create_unique_constraint("uq_allocation_import_key", ["engagement_id", "import_key"])


def downgrade() -> None:
    with op.batch_alter_table("allocation") as batch:
        batch.drop_constraint("uq_allocation_import_key", type_="unique")
        batch.drop_column("import_key")
