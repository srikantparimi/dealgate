# S10-01 — SOW upload pipeline

## Story

The SOW is the input. The client is read from the SOW. A person uploads a
file; the system creates the client (if new), the opportunity (if new),
the SOW version, the extracted-fields envelope, the classification, the
staffing plan, the GM sheet and the approver route. The person confirms
what the system decided. There is no dropdown to pick a client before
upload. There is no HubSpot dependency.

Kanna Parimi, product owner, 19 September 2026. This story replaces every
earlier scoping around the upload flow.

## Backend

### `POST /sows/upload` (multipart)

Fields:

- `file` (required): the PDF or DOCX.
- `client_hint` (optional): text the user typed if they insisted; does not
  gate the request.

Pipeline (in one request, then a background job for the slow steps):

1. **Hash first.** SHA-256 the bytes. If a `sow_version` with the same
   `file_hash` exists, return `{ status: "duplicate", sow_version_id, opportunity_id }`
   (HTTP 200). Never re-upload the same bytes.
2. **Document-type gate.** `services/document_type.py`: rules-first
   (headers like "STATEMENT OF WORK", "SCOPE OF WORK", "MASTER SERVICES
   AGREEMENT" score toward `sow` / `msa`; "CURRICULUM VITAE", "EXPERIENCE"
   score toward `resume`; invoice glyphs toward `invoice`). Bedrock
   fallback when rules are ambiguous. Reject any file that is not
   `sow | msa | nda` with HTTP 422 `{ detected_type, message }`. The
   message is human: `"This file does not look like a SOW. Detected:
   résumé."`. Do NOT create any DB rows.
3. **Presign + upload.** Get a PutObject presigned URL for the ingest
   bucket, stream the bytes, verify the hash after upload.
4. **Extract.** `services/sow_extract.py` already exists. Extend it to
   also return `client_signals`: `{ legal_name, domain, aliases, address_lines }`.
5. **Resolve client.** `services/client_resolver.py` (new). Match
   candidates by:
   - exact legal name (score 1.0)
   - domain match (0.95)
   - alias match against `client_alias` table (0.9)
   - fuzzy name (rapidfuzz ratio > 0.85)
   Return `{ resolution: "matched", client_id }` if the top score is
   ≥ 0.85 AND ≥ 0.15 above the second. Otherwise return
   `{ resolution: "needs_pick", candidates: [top 3], create_new: { legal_name, domain, address_lines } }`.
6. **Auto-create opportunity** when resolution is "matched". Fields:
   `source='sow_upload'`, `hubspot_deal_id=NULL`, `owner_id=<uploader>`,
   `client_id=<resolved>`, `governance_status='Intake'`. When resolution
   is "needs_pick", the opportunity is created only after the picker
   returns.
7. **Chain classifier → auto-staffing → auto-GM → approver routing** exactly
   as `docs/directives/sow-first.md` specifies. Each step writes an
   `audit_event`.
8. **Job envelope.** Return `{ job_id, sow_version_id?, opportunity_id? }`
   immediately. `GET /sows/jobs/{job_id}` returns
   `{ status: "queued"|"extracting"|"classifying"|"matching_client"|"deriving_gm"|"needs_pick"|"done"|"failed", opportunity_id?, sow_version_id?, resolution?, error? }`.

### `POST /sows/jobs/{job_id}/pick`

Body: `{ client_id }` OR `{ create_new: { legal_name, domain, ...} }`.
Effect: creates the client if requested, links the opportunity, resumes
the pipeline. Idempotent by `(job_id, client_id | create_new.legal_name)`.

### Data model additions

- `opportunity.source ENUM('hubspot','sow_upload','bulk_import','manual') NOT NULL DEFAULT 'hubspot'`.
- `opportunity.hubspot_deal_id` becomes nullable (was unique NOT NULL). Add a
  partial unique index `WHERE hubspot_deal_id IS NOT NULL`.
- `client_alias(client_id, alias TEXT, source TEXT)`.
- `sow_upload_job(id UUID pk, uploader_id, s3_key, file_hash, status, resolution, error, created_at, updated_at, opportunity_id NULL, sow_version_id NULL, needs_pick_payload JSONB NULL)`.

### Permissions

- Sales, Delivery, Finance, Legal, CEO, SysAdmin can upload. Reviewer roles
  see only their own uploads in the job list.
- Audit event per pipeline step.

## Frontend

### `web/src/pages/v2/SowStudio.tsx`

- **UploadFlow**: rewrite. `UploadPanel` submits `file` only. On response,
  navigate to `/sows/new?jobId=<id>` and render a `PipelineProgress` panel
  (Extracting → Classifying → Matching client → Deriving GM). When status
  is `needs_pick`, render a `ClientPickerModal` with top-3 candidates +
  "Create new" pre-filled from the SOW. When status is `done`, redirect
  to `/sows/new?opportunityId=<id>`.
- **UploadPanel** (`sow-studio/confirmation/UploadPanel.tsx`): remove
  Client field entirely. The only precondition is a file. Submit label
  reads "Upload & derive". Show a soft, inline note: "Client is read from
  the SOW."
- **PipelineProgress**: 5 rows, each with a spinner / check / warning
  chip. When a step fails, show the error and a "Retry from this step"
  button (calls `POST /sows/jobs/{job_id}/retry`).
- **ClientPickerModal**: three radio candidates + "Create new client".
  Provenance chip on every field. "Create new" pre-fills from the SOW
  extraction so the reviewer confirms, does not type.
- **Non-SOW error**: 422 payload → red banner with the detected-type
  message + "Upload a different file" button. No DB rows are created.

## Tests

- `api/tests/test_sow_upload_router.py`
  - happy path: PDF fixture → job goes queued → done, opportunity + sow +
    gm exist, audit chain intact, confirmation payload returns provenance.
  - résumé.pdf → 422 with `{ detected_type: "resume" }`, no rows.
  - re-upload same bytes → `{ status: "duplicate" }`, no new rows.
  - unknown client → `needs_pick` with 3 candidates + create_new; POST
    /pick with `create_new` → client created, opp linked, pipeline resumes.
  - role gate: uploader stored, non-uploader cannot see the job.
- `web/src/__tests__/v2/SowStudio.upload.test.tsx`
  - button enables the moment the file is attached (no client selection).
  - non-SOW banner renders on 422.
  - picker modal renders 3 + create-new; picking one navigates to the
    confirmation URL.
- `tests/e2e/specs/14-sow-upload-happy.spec.ts`: upload → progress →
  confirmation, all in one flow, against the real backend.
- `tests/e2e/specs/15-sow-upload-non-sow.spec.ts`: résumé rejected.
- `tests/e2e/specs/16-sow-upload-new-client.spec.ts`: unknown client
  picker → create new → confirmation.

## Definition of done

- A human can drag a PDF onto `/sows/new` and reach the confirmation
  screen on staging without picking a client, without a HubSpot deal.
- `grep -r "not wired\|TODO: stub\|Not implemented\|Follow-up story" api/ web/`
  returns nothing.
- All tests green locally and in CI.
