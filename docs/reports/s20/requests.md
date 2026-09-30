# S20 · cross-worker requests (Lead routes)

Workers append a block here whenever they need a change on a file they
don't own (per `contracts.md` §6) — the Lead applies within the hour and
tags the responsible worker + a link to the requesting commit.

Format:
```
## <Wn>-<UTC>-<seq> · <one-line title>
Reason: <why>
File(s): <paths>
Change: <exact behavior/API>
Rollback: <how to undo>
Test: <acceptance>
Requested-in: <sha of requesting commit or `plan-only`>
```

---

(seeded empty; workers append during their runs)

---

## W1-20260930T0700-01 · sync_status watermark columns (D4, contracts §5)

Reason: contracts §5 names nine watermark keys — the existing
``sync_status`` schema only tracks ``last_success_at`` / ``last_error``
/ ``cursor``, which the review flagged as "worker heartbeat, not
freshness". D4 replaces heartbeat with typed clocks.

File(s): `api/alembic/versions/2026093X_W1_01_sync_status_watermarks.py` (Lead-numbered).

Change: **new alembic revision, backward-compatible** — every added
column nullable, no drop of populated columns. Model change already
landed in `api/app/models/sync_status.py` on this branch; the migration
just needs to match.

```python
def upgrade() -> None:
    op.add_column("sync_status", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sync_status", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sync_status", sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sync_status", sa.Column("scan_generation", sa.Integer(), nullable=True))
    op.add_column("sync_status", sa.Column("scan_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sync_status", sa.Column("scan_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sync_status", sa.Column("backlog_age_seconds", sa.Integer(), nullable=True))
    op.add_column("sync_status", sa.Column("dlq_age_seconds", sa.Integer(), nullable=True))

def downgrade() -> None:
    op.drop_column("sync_status", "dlq_age_seconds")
    op.drop_column("sync_status", "backlog_age_seconds")
    op.drop_column("sync_status", "scan_completed_at")
    op.drop_column("sync_status", "scan_started_at")
    op.drop_column("sync_status", "scan_generation")
    op.drop_column("sync_status", "reconciled_at")
    op.drop_column("sync_status", "processed_at")
    op.drop_column("sync_status", "received_at")
```

Rollback: `alembic downgrade -1` on the new revision. Backward-compat
because every existing reader (`app.services.sync_status.touch_source`)
feature-detects each column with `hasattr` before writing.

Test: `api/tests/test_hubspot_sync_watermarks.py` — 8 tests pass on the
SQLite path (metadata `create_all` picks the columns up automatically).

Requested-in: <this commit>


## W1-20260930T0700-02 · hubspot_owner mirror table (D2)

Reason: D2 requires a persistent owner mirror including archived owners
so the deal sales owner always resolves ("Owner details unavailable" vs
"Unassigned", per T04 / T31).

File(s): `api/alembic/versions/2026093X_W1_02_hubspot_owner.py` (Lead-numbered).

Change: **new table `hubspot_owner`**. Model class
:class:`HubspotOwner` lives in `api/app/services/hubspot_owners.py` on
this branch (auto-registers on `Base.metadata` at import time). Lead
may want to move it to `api/app/models/hubspot_owner.py` for
convention; either way the migration is:

```python
def upgrade() -> None:
    op.create_table(
        "hubspot_owner",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hubspot_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hubspot_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_hubspot_owner_email", "hubspot_owner", ["email"])
    op.create_index("ix_hubspot_owner_archived", "hubspot_owner", ["archived"])

def downgrade() -> None:
    op.drop_index("ix_hubspot_owner_archived", table_name="hubspot_owner")
    op.drop_index("ix_hubspot_owner_email", table_name="hubspot_owner")
    op.drop_table("hubspot_owner")
```

Also add `from app.services.hubspot_owners import HubspotOwner  #
noqa: F401` (or re-export from a new `app.models.hubspot_owner` module)
inside `api/app/models/__init__.py` so alembic's `env.py` picks the
mapper up when it introspects `Base.metadata`.

Rollback: `alembic downgrade -1` drops the table; no dependent rows
exist yet.

Test: `api/tests/test_hubspot_owners_mirror.py` — 4 tests pass.

Requested-in: <this commit>


## W1-20260930T0700-03 · hubspot_property_mapping table (D10)

Reason: D10 requires persisting the discovered Business Unit property
mapping (object type, options, label). Model class
:class:`HubspotPropertyMapping` lives in
`api/app/services/hubspot_properties.py` on this branch.

File(s): `api/alembic/versions/2026093X_W1_03_hubspot_property_mapping.py`.

Change: **new table `hubspot_property_mapping`**.

```python
def upgrade() -> None:
    op.create_table(
        "hubspot_property_mapping",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("internal_name", sa.String(128), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("field_type", sa.String(32), nullable=False),
        sa.Column("options", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

def downgrade() -> None:
    op.drop_table("hubspot_property_mapping")
```

Same `models/__init__.py` re-export note as W1-...-02.

Rollback: `alembic downgrade -1`.

Test: `api/tests/test_hubspot_property_discovery.py` — 6 tests pass.

Requested-in: <this commit>


## W1-20260930T0700-04 · services/hubspot_pipeline.py — group by (pipeline_id, stage_id) (D9)

Reason: D9 says stage aggregation must group by `(pipeline_id,
stage_id)`, not by `stage_label`. Same-label stages across different
pipelines currently collapse into one bucket, and the "Included 100 /
Excluded 0" wording in the Portfolio report exposes that this
aggregation is skew-prone.

File(s): `api/app/services/hubspot_pipeline.py` (W2-owned).

Change: rewrite `list_pipeline_deals`'s count query and `list_clients`'
per-client `breakdown_stmt` to group by
`(Opportunity.hubspot_pipeline_id, Opportunity.hubspot_stage_id,
Opportunity.currency)` — then resolve `stage_label` from the mirror
for display *after* aggregation. Explicit unknown-stage bucket for
rows where both `hubspot_pipeline_id` and `hubspot_stage_id` are null.
Zero-count stages rendered by joining onto the full pipelines/stages
metadata rather than the observed set.

Rollback: revert to `.group_by(Opportunity.stage_label,
Opportunity.sales_stage)` — the S19 shape.

Test: **new W5 test** `tests/test_pipeline_stage_aggregation_ids.py`:
insert two deals with identical `stage_label = "Proposal"` but
different `hubspot_pipeline_id`, assert the response has two buckets.

Requested-in: <this commit>


## W1-20260930T0700-05 · models/__init__.py — re-export new HubSpot models

Reason: `HubspotOwner` and `HubspotPropertyMapping` are declared in
`api/app/services/hubspot_owners.py` /
`api/app/services/hubspot_properties.py` on this branch (W1-owned
services). They register on `Base.metadata` at import time, so SQLite
tests already see them; but on Postgres the alembic `env.py` only
imports `app.models` before autogenerating, so the new tables never
show up in a generated migration diff.

File(s): `api/app/models/__init__.py`.

Change: add two `noqa`-annotated imports so the mappers register when
`app.models` is imported:

```python
from app.services.hubspot_owners import HubspotOwner  # noqa: F401,E402
from app.services.hubspot_properties import HubspotPropertyMapping  # noqa: F401,E402
```

(Or, preferably, move the model classes to
`api/app/models/hubspot_owner.py` and
`api/app/models/hubspot_property_mapping.py` and add normal exports —
the W1 services keep their behaviour by importing from there.)

Rollback: revert the imports; the tables will still be created by
the migrations but alembic autogenerate will flag them as unknown on
the next diff.

Test: `test_migration_parity.py` (postgres-gated) passes after apply.

Requested-in: <this commit>

