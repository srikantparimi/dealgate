# S10-02 — Bulk SOW import

## Story

SmarTek21 has live contracts today. A governance system that only sees
new SOWs forces one set of deals outside and one inside — the exact
condition we are trying to end. Build **Bulk SOW import** as a
first-class screen under **Settings & controls → Data imports**, linked
from the SOW approvals board ("Import legacy SOWs" secondary action).

Every imported record enters the same pipeline as a single upload. One
pipeline, two entry points.

Kanna Parimi, product owner, 19 September 2026.

## Backend

### `POST /admin/bulk-imports/sows`

Multipart. Accepts either a set of files or a ZIP. Creates an
`import_batch` row, enqueues one `import_file` row per file, returns
`{ batch_id }`.

### `GET /admin/bulk-imports/{batch_id}` and `GET /admin/bulk-imports/{batch_id}/files`

Returns the batch and per-file rows for the queue view. Each file's
`status ∈ { queued, extracting, classifying, matching_client, deriving_gm, needs_review, imported, rejected, duplicate }`.

### Worker

For every file:

1. Hash. If a `sow_version.file_hash` matches, mark `duplicate`, link
   `duplicate_of = existing_sow_version_id`, done.
2. Document-type gate. If not `sow | msa | nda`, mark `rejected` with the
   detected type; do not create records.
3. Non-SOW agreements (MSA / NDA) route to `services/agreements.py`:
   file against the resolved legal entity, do not create a SOW.
4. SOW path: run the same chain as single upload (extract → classify →
   resolve client → create opportunity `source='bulk_import'`,
   `hubspot_deal_id=NULL` → auto-staff → auto-GM).
5. Set `governance_status='legacy_not_evidenced'` on the sow_version. Do
   NOT create approval rows. Do NOT flip `approval_evidenced=True`.
6. If the SOW has a signature page or the reviewer confirms it later,
   set `execution_state='executed'` and create the renewal schedule and
   notice-deadline task from the extracted term dates immediately. A SOW
   already inside its two-month notice window opens a renewal review on
   import.
7. If staffing cannot be derived (no resource table and no template
   inference), the GM sheet is `incomplete`. It shows up on the Finance
   dashboard as "missing cost input". Never zero. Never fabricated.
8. When any `needs_you` field remains after the pipeline, status is
   `needs_review` and the file appears in the Needs-review queue.

### Second dedupe pass (after hash)

Within a batch and against the persisted set: `(client_id, sow_title,
term_start, term_end)`. Any hit is marked `duplicate` and linked.

### Data model additions

- `import_batch(id, run_by, created_at, updated_at, status, file_count, rejected_count, duplicate_count, imported_count, note TEXT)`.
- `import_file(id, batch_id, filename, size, sha256, detected_type, status, matched_client_id, matched_confidence, opportunity_id, sow_version_id, duplicate_of, warnings JSONB, errors JSONB, created_at, updated_at)`.
- `sow_version.governance_status ADD value 'legacy_not_evidenced'`
  (application-side enum; DB column is TEXT).
- `sow_version.execution_state ENUM('draft','executed','superseded') DEFAULT 'draft'`.

### `GET /admin/bulk-imports/{batch_id}/log.csv`

Streams the log: `batch_id, filename, sha256, size, detected_type,
status, matched_client, confidence, opportunity_id, sow_version_id,
warnings, errors, created_at, updated_at, record_url`.

Idempotent re-run: re-uploading the same batch produces the same set of
records (duplicates flagged, nothing re-created).

## Frontend

### `web/src/pages/v2/BulkSowImport.tsx` (new)

Route: `/settings/data-imports/sows`. Link from Settings sidebar and
from a secondary action on the SOW approvals board.

Layout:

- Header: title, "Drop files or ZIP" dropzone that opens the file picker.
- After drop: **Batch queue table**. Columns: file, size, detected type,
  status chip, matched client, confidence, actions (Open record, Retry,
  View errors).
- Right-side summary: totals (queued / extracting / needs review /
  imported / rejected / duplicate), "Download log CSV" button, "Run
  again" (idempotent) button.
- Row click → confirmation screen for that sow (same screen as single
  upload; carries `?jobId=<file_id>&opportunityId=<opp>`).

### `web/src/pages/v2/NeedsReviewQueue.tsx` (new, under **My work**)

Lists every imported record with a `needs_you` field. Row click opens
the confirmation screen. Nothing else in the system waits for this
queue — reviewers clear them one by one.

### Legacy chip

`StatusBadge tone="neutral" label="Legacy"` on:

- SOW approvals board cards
- Command Center delivery-economics table
- Client page SOW list
- Renewals list
- Reporting exports

## Tests

- `api/tests/test_bulk_import_pipeline.py`
  - 6 fixture SOWs + 1 MSA + 1 duplicate file → 8 rows, 7 records, 1
    duplicate. MSA filed against its legal entity.
  - SOW with term_end 45 days out → renewal review + notice task created
    on import.
  - Re-running the same batch → idempotent (no new records, log matches).
- `web/src/__tests__/v2/BulkSowImport.test.tsx`
  - status chips render for every state, totals recompute, CSV button
    fires.
- `tests/e2e/specs/17-bulk-import.spec.ts`: happy path against staging.
- `tests/e2e/specs/18-bulk-import-duplicate.spec.ts`: duplicate flagged.

## Definition of done

- On staging, a human uploads the six fixtures + one MSA + one
  duplicate; the queue shows 8 rows with the right states; CSV
  downloads; a 45-day-out SOW shows a renewal review; the Legacy chip
  is visible everywhere the record surfaces.
