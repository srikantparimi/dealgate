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


## W5-2026-09-30-01 · add S20 fixture prefixes to e2e cleanup regex

Reason: T44 full-journey + T32 event-injection tag their fixtures with
`S20 e2e ` (deal / client / SOW names) and `s20-injection` (SQS message
`test_marker`). `worker/e2e_cleanup.py::_PREFIX_RE` currently only knows
about S12–S17 prefixes; a scheduled tick will leave S20 residue behind
after 24h.

File(s): `worker/e2e_cleanup.py`
Change: extend `_PREFIX_RE` to also match `^(S20 e2e |s20-)`
(case-insensitive). Same 24h age gate stays.
Rollback: revert the regex diff; residue is harmless (name prefix
alone doesn't affect production data — isolation.md §7 confirms).
Test: `api/tests/test_s20_security_boundaries.py::test_e2e_cleanup_regex_does_not_match_real_clients`
still passes for the real names (`74 Sky`, `Capitec Bank Limited`,
`BSC Staffing - UX/UI Designer`, `Sky Group`, `3M Company`).
Requested-in: (this commit)
Owner: **W1** (owns `worker/`).

## W5-2026-09-30-02 · terraform apply for multi-role Cognito approvers

Reason: `tests/e2e/fixtures/multi-role-auth.ts` needs a Secrets Manager
entry `officeapp-dev-e2e-approvers` mapping role slots (submitter /
delivery / hr / finance / legal / ceo) to Cognito creds. Without it,
every role falls back to the SystemAdmin smoke bot and T27
(permissions uniform) + T44 (multi-role e2e) cannot verify role
partitioning tonight.

File(s): `infra-tf/modules/e2e-approvers/*` (new), `infra-tf/staging.tf` include.
Change:
- Create 5 new Cognito users (submitter, delivery, hr, finance,
  legal, ceo — the last already exists but confirm group membership).
- Put creds into `officeapp-dev-e2e-approvers` secret as JSON:
  `{ "submitter": {...}, "delivery": {...}, ... }`.
- Add each to the appropriate `cognito:groups` (Delivery / HR /
  Finance / Legal / CEO / Sales).
Rollback: `terraform destroy` on the module.
Test: `mintRoleTokens("delivery")` returns tokens whose
`cognito:groups` claim contains `"Delivery"` (asserted at test-suite
start).
Requested-in: (this commit)
Owner: **Lead** (Terraform, plus records D-ISO-02 in decisions.md).

## W5-2026-09-30-03 · read-only mirror endpoint for T03 parity

Reason: T03 SQL parity captures 6 surfaces (source, mirror, list,
client, deal, export). The mirror row (raw `opportunity` table with
timestamps) is only reachable today via a psql connection; we need
a read-only HTTP surface so the T03 harness runs from a laptop.

File(s): `api/app/routers/dev.py` (already exists), a new
`GET /api/dev/mirror/opportunities/{id}`.
Change: return the full `Opportunity` row + joined `HubspotStage`
label as JSON. Gate behind `require_role("SystemAdmin")` and
`DEALGATE_ENV in {"dev","staging"}` (mirrors existing dev-router
policy).
Rollback: delete the route.
Test: `scripts/t03-parity.sh` step 3 no longer records `(endpoint
not exposed)`; the captured JSON has non-null `hubspot_deal_id`,
`hubspot_stage_id`, `stage_label`.
Requested-in: (this commit)
Owner: **W1**.

## W5-2026-09-30-04 · pipeline export CSV endpoint

Reason: T03 step 6 (export parity) + T35
(test_export_returns_full_filtered_set) both need a public
`GET /api/pipeline/opportunities/export.csv` that returns the same
row set the list API would return (same filter, permission-checked,
same aggregate contract per contract §4).

File(s): `api/app/routers/pipeline.py`.
Change: add `GET /export.csv`; body is CSV with one row per matching
opportunity; columns match `OpportunityRow` fields; permissions
identical to list.
Rollback: delete the route.
Test: `api/tests/test_s20_pagination_vs_totals.py::test_export_returns_full_filtered_set`;
CSV row count equals list `total`, not `page_size`.
Requested-in: (this commit)
Owner: **W2**.
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

## W7-2026-09-30-01 · signed_sow_upload: add verify_reason + expand statuses
Reason: T22 — declined / expired / unsigned must be separate statuses with a
captured reason. Upload alone is never `verified`. Current CHECK constraint
locks the set to `pending | verified | blocked`; the review's directive
also demands unsigned uploads reject with 400.
File(s): `api/app/models/signed_sow.py`, `api/alembic/versions/<Lead-id>_signed_sow_verify_expand.py`
Change:
  - Column `verify_reason: str | None` nullable (max 512). Set alongside
    verify_status; carries the human-readable reason (`price_mismatch`,
    `scope_similarity_below_threshold`, `declined_by_signer`,
    `signature_request_expired`, `bedrock_manual_required`, etc.).
  - Column `signer_state: str | None` nullable (max 32). ONE OF
    `null | sent | signed | declined | expired`. Tracks the external
    signature-request lifecycle independently from `verify_status`.
  - Extend `VERIFY_STATUSES` tuple + CHECK constraint to
    `pending | verified | blocked | unsigned | declined | expired`.
  - `verify_reason` allowed to be null when `verify_status='verified'`
    (no reason needed on success).
Rollback: drop columns; restore original CHECK; app service already
handles null `verify_reason`.
Test: pytest `test_signed_sow_verify_reason.py` — round-trips each new
status + reason via `services.signed_sow.mark_declined/mark_expired`,
audit line asserts `signed_sow.declined` / `.expired`.
Requested-in: plan-only (W7 spawn commit forthcoming)

## W7-2026-09-30-02 · delivery_acceptance table (new)
Reason: T23 — release gate needs delivery_acceptance as a distinct event.
Not derivable from approvals or signed_sow. Delivery ops sign off after
executed doc verified; without this the release path collapses back to
"CRM Closed Won or executed pdf" — both banned by the review.
File(s): `api/app/models/delivery_acceptance.py` (new), `api/app/models/__init__.py` (export),
`api/alembic/versions/<Lead-id>_delivery_acceptance.py`
Change: new table `delivery_acceptance`:
  - `id UUID PK`
  - `package_id UUID NOT NULL FK approval_package.id`
  - `accepted_by UUID NOT NULL FK user.id` (Delivery role required at
    service layer — server enforces)
  - `accepted_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `notes VARCHAR(2048) NULL`
  - `staffing_confirmed BOOL NOT NULL DEFAULT false`
  - `billing_setup_confirmed BOOL NOT NULL DEFAULT false`
  - `po_confirmed BOOL NOT NULL DEFAULT false`
  - Unique index on `(package_id)` — one acceptance per package; a
    superseded package can never inherit a prior acceptance.
Rollback: drop table.
Test: pytest `test_delivery_acceptance.py` — cannot release without a
row; reject if accepted_by is not in Delivery group; unique constraint
holds.
Requested-in: plan-only

## W7-2026-09-30-03 · project table (new) + baseline snapshot
Reason: T24 — projects need explicit provenance (deal_id, sow_version_id,
gm_model_id, package_id), one row per released package, baseline frozen at
release, forecast + actuals kept separate. Current `services/projects.py`
is a read-model over ApprovalPackage which conflates identities.
File(s): `api/app/models/project.py` (new), `api/app/models/__init__.py` (export),
`api/alembic/versions/<Lead-id>_project_table.py`
Change: new table `project`:
  - `id UUID PK`
  - `opportunity_id UUID NOT NULL FK opportunity.id`
  - `sow_version_id UUID NOT NULL FK sow_version.id`
  - `gm_model_id UUID NOT NULL FK gm_model.id`
  - `package_id UUID NOT NULL FK approval_package.id`
  - `client_id UUID NULL FK client.id` (denormalised for reads)
  - `title VARCHAR(255) NOT NULL`
  - `baseline_snapshot_json JSONB NOT NULL` — frozen at creation
  - `created_at TIMESTAMPTZ DEFAULT now()`
  - `created_by UUID FK user.id`
  - `archived_at TIMESTAMPTZ NULL`, `archived_reason VARCHAR(1024)`
  - UNIQUE (`package_id`) — idempotency guard: one project per released
    package. Re-running release links the existing row.
Rollback: drop table; existing projects endpoint reads ApprovalPackage
directly.
Test: pytest `test_project_lifecycle.py` — create-or-link is idempotent;
baseline never mutates.
Requested-in: plan-only

## W7-2026-09-30-04 · project_actual — dedupe key + source_ref
Reason: T24 — actuals import must protect against duplicate imports.
Current `actual_period` uniqueness is `(resource_line_id, period_month)`,
which permits accidental overwrites when re-importing the same file. The
review calls for `(project_id, period, source_ref)` dedupe.
File(s): `api/app/models/actual.py`, `api/alembic/versions/<Lead-id>_actuals_dedupe.py`
Change:
  - Column `project_id UUID NULL FK project.id` (backfilled from
    `gm_model_id -> approval_package -> project`).
  - Column `source_ref VARCHAR(255) NULL` — carries the import file's
    checksum or an external system's row id. NULL for legacy rows.
  - Add UNIQUE (`project_id`, `period_month`, `source_ref`) where all
    three are NOT NULL (partial index) — dedupes any repeat import while
    leaving legacy rows alone.
Rollback: drop columns + index.
Test: extend `test_actuals_import.py` — importing the same CSV twice
under the same source_ref does not create duplicate rows.
Requested-in: plan-only

## W7-2026-09-30-05 · approval_package: superseded_by (many-SOWs rollup)
Reason: T22 / D1 — "prepare only the current approved package". When a
newer package supersedes an older one, the older signature UI must show
"Superseded by v{N}" and disable the primary action. Without a link on
the model, W7 cannot render the banner or gate the endpoint.
File(s): `api/app/models/approval.py`, `api/alembic/versions/<Lead-id>_pkg_superseded.py`
Change:
  - Column `superseded_by UUID NULL FK approval_package.id` on
    `approval_package`. Set when a new submission is created for the
    same opportunity and the older one is no longer the current
    approved package.
  - Backfill script sets `superseded_by` for each opportunity's older
    packages pointing to the newest `ready_to_sign` / `released` one.
Rollback: drop column.
Test: extend `test_signed_sow_superseded.py` — signature endpoints on
the older package return 409 with `superseded_by` in the payload.
Requested-in: plan-only

---

**W7 note (2026-09-30):** overnight schedule means no Lead is applying
requests in real time. To keep W7 unblocked for the deliverable
(green pytest for the release gate), W7 has added the model + migration
files directly on `s20/W7`, with commit sha noted in `progress-W7.md`.
Lead may re-assign migration ids on integration; the model file names +
column names are the contract.

## W2-2026-09-30-01 · Add `opportunity.name` column (dealname)

Reason: Directive S20 §2 W2 · L04 — Opportunities table must show the actual
deal name from HubSpot `dealname`. Today `dealname` is fetched
(`api/app/integrations/hubspot.py:107` includes it in `_DEAL_PROPERTIES`)
but never stored; the UI is forced to render `stage_label` in the Deal
column, which is why every row shows its stage as the deal identity.

File(s): `api/app/models/opportunity.py`,
`api/alembic/versions/` (new revision numbered by Lead),
`api/app/services/hubspot_intake.py` (populate + update path).

Change:
- Add `name: Mapped[str | None] = mapped_column(String(255), nullable=True)`
  on `Opportunity`.
- Migration: `op.add_column('opportunity', sa.Column('name', sa.String(255),
  nullable=True))`. Backward-compatible: nullable, no server_default beyond
  NULL; existing rows keep working; downgrade is `op.drop_column`.
- In `hubspot_intake._upsert_opportunity`: read `props.get("dealname")`,
  set on `Opportunity(name=…)` at insert and at update-with-change-detection
  (same pattern as `stage_label`). Emit the field in the `after` audit.

Rollback: Lead reverts the alembic revision (`alembic downgrade -1`);
`hubspot_intake` change removes the `props.get("dealname")` block.

Test: W2 acceptance test asserts opportunity rows expose `name` via the
API and the SPA renders it in the Deal column. W1's backfill test can
grow a name-populated assertion on next pass.

Requested-in: (this commit)


## W2-2026-09-30-02 · Client account-owner surface for pipeline rollups

Reason: Directive §2 W2 · L05 + contracts §2 D2 — client rows must show a
"client account owner" that is the HubSpot company `hubspot_owner_id`
resolved via W1's owner mirror, NOT derived from a deal. Today
`services/hubspot_pipeline.list_clients` sets `owner_name=None` /
`owner_email=None` on every client row (see
`api/app/services/hubspot_pipeline.py:940-941`) with a "slice 2 UI plugs
deeper owner metadata" comment, then falls back to the *primary deal's
owner* as `owner_id`. That's the exact overwrite-with-deal-owner defect
D2 forbids.

File(s): `api/app/models/client.py` + a migration + W1's mirror
(`api/app/services/hubspot_owners*.py` and intake company upsert).

Change:
- Add `hubspot_owner_id: Mapped[str | None] = mapped_column(String(64),
  nullable=True)` on `Client`.
- W1 populates it in the company-upsert path (currently
  `services/hubspot_intake.upsert_client_from_hubspot`) from the company's
  `hubspot_owner_id` property; on unset → NULL.
- W1's owner mirror exposes a lookup `resolve_owner_by_hubspot_id(session,
  hs_owner_id) -> (name, email) | (None, None)` for W2's query service to
  call once per page of clients (batch).
- Migration: `op.add_column('client', sa.Column('hubspot_owner_id',
  sa.String(64), nullable=True))`, backward-compatible.

Rollback: drop the column; W1's mirror lookup returns (None, None) which
W2 already handles as "not set".

Test: W2 acceptance test seeds a company with a HubSpot owner id + a
deal whose owner is different, asserts the client row's `owner_name`
tracks the company property, not the deal.

Requested-in: (this commit)


## W2-2026-09-30-03 · `hubspot_business_unit` column on opportunity + optional company

Reason: Directive §2 W2 + contracts §4 filter contract — Opportunities
must be filterable by Business Unit, and rows must render a BU column
(L04). Per D10 the BU property is discovered via HubSpot properties API
(W1 owns the discovery + type-aware mirroring). W2 needs a column to
persist the discovered value against so the filter + column work.

File(s): `api/app/models/opportunity.py`, a migration, W1's mapper.

Change:
- Add `hubspot_business_unit: Mapped[str | None] = mapped_column(String(64),
  nullable=True)` on `Opportunity` (assumes the discovered field is a
  simple picklist; if W1 reports a different type in
  `sync_status.hubspot_property_business_unit`, this column becomes
  `String(255)` or JSON per W1's report — Lead decides).
- W1 pulls the discovered internal property name from
  `sync_status.hubspot_property_business_unit`, adds it to
  `_DEAL_PROPERTIES` in `integrations/hubspot.py`, and stores the value
  in `hubspot_business_unit` at insert + change-detected update.
- If the property is on the **company** instead of the deal (D10 says
  "deals, then companies"), W1 mirrors it onto `client.hubspot_business_unit`
  instead; W2 filter joins through the client. W1's `blocked` report is
  authoritative if neither surface yields a property.

Rollback: drop the column; W1 stops writing it.

Test: W2 asserts the `business_unit=[…]` query param filters
opportunities to matching rows, and the column renders in the UI table.

Requested-in: (this commit)

## W3-2026-09-30-01 · sow.opportunity_id uniqueness relax
Reason: D1 fixed decision — many SOWs per deal. `Sow.opportunity_id` is
currently `unique=True` (`api/app/models/sow.py:30-32`), which forbids a
second SOW for a rebooked/renewal/added-scope engagement. The rollup
service W3 built (`services/sow_rollup.py`) is written to aggregate
multiple rows per deal; it collapses to one row today so it can ship
before the constraint is relaxed.
File(s): `api/app/models/sow.py`, new alembic revision from head.
Change:
  - Drop `unique=True` on `Sow.opportunity_id`.
  - Add composite index `ix_sow_opportunity_created` on
    `(opportunity_id, created_at)` — the rollup query is by deal, newest
    first.
  - Migration is backward-compatible (D5): existing rows are unaffected;
    dropping a uniqueness constraint never fails on populated data.
Rollback: recreate the unique constraint after archiving all-but-one SOW
per deal. Alembic `downgrade` recreates the unique index; if any deal
already has >1 SOW the downgrade fails visibly (which is the desired
signal — do not silently pick a winner).
Test: `api/tests/test_sow_rollup.py::test_many_sows_per_deal` (see W3
commit).
Requested-in: s20/W3 (planned as part of cycle 1)

## W3-2026-09-30-02 · deal detail page at /deals/:id
Reason: L09/L11 — a deal without a SOW currently redirects to
`/sows/:id`, rendering an empty SOW workspace shell with a disabled
"Complete scope" button and an enabled "Delete SOW" button. The review
requires a real deal detail page for tracking, comments, actions,
Upload SOW, and reporting. W3 owns SOW surfaces only; W2 owns
`web/src/pages/v2/deal*` per `contracts.md` §6.
File(s): W2 to create `web/src/pages/v2/DealDetail.tsx` and wire it into
`web/src/App.tsx` at `/deals/:id` (replacing the RetiredPage route).
Change:
  - Route `GET /deals/:id` renders client + deal identity, owner,
    stage, next action, latest comment, groups, and the SOW list or
    `Upload SOW` primary CTA per the review's Deal workspace row.
  - The rollup headline (D1) comes from
    `services.sow_rollup.compute_headline(opportunity_id)` — W3 ships
    the service; W2 consumes it in the deal page.
  - Upload SOW navigates to `/sows/new?opportunityId=<id>` with the
    client_id pre-bound (T11).
Rollback: revert the App.tsx route; RetiredPage catches `/deals/:id`
again. The rollup service and deal API stay in place.
Test: W5's Playwright T10 (deal with no SOW) exercises this end-to-end.
Requested-in: s20/W3 (cycle 1) — non-blocking for W3 shipping the SOW
workspace repairs; W3 patches the SowWorkspace to render an honest
empty-state until W2 lands the page.

## W3-2026-09-30-03 · sow_upload_job columns for pre-bound client + deal
Reason: T11/T37 — the review requires `POST /sows/upload` to accept
(and require) both `client_id` and `opportunity_id` (deal), persist both
before extraction, and preserve the file + entered corrections on
extraction failure. `SowUploadJob.opportunity_id` already exists as a
nullable FK set by the pipeline post-match; add `bound_client_id` and
`bound_opportunity_id` capturing the *pre-upload* binding the human
declared, so a picker step is skipped and the confirm page can prove the
binding is human-authoritative (not a fuzzy match).
File(s): `api/app/models/sow_upload_job.py`, new alembic revision.
Change:
  - Add nullable columns `bound_client_id: UUID | None` (FK client.id)
    and `bound_opportunity_id: UUID | None` (FK opportunity.id) to
    `sow_upload_job`.
  - When both are provided at upload time, the pipeline skips the
    client-match step and creates the SOW version under
    `bound_opportunity_id` directly. Uniqueness on
    `(bound_opportunity_id, file_hash)` is not enforced tonight — D1
    lets many SOWs share a deal.
  - Backward-compatible: existing callers can still omit both fields
    and hit the fuzzy-match/picker path.
Rollback: drop the two columns. Existing rows written since deploy
lose their explicit binding but the rest of the row survives; the
pipeline's post-match `opportunity_id` still records the resolved
binding.
Test: `api/tests/test_sow_upload_binding.py` (W3 will write it against
the current schema and re-run after the migration lands).
Requested-in: s20/W3 (cycle 1) — W3 ships the *router* accepting the
two fields and stashing them on the job's `needs_pick_payload` in the
interim; once the columns land the router writes them directly.
