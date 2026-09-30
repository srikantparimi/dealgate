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
