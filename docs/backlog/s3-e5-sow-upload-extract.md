# S3 E5 — SOW upload + AI extraction + human confirm

## User story
As the account owner, I upload the SOW (PDF or docx) on the Deal detail
page. The system extracts the key fields (scope summary, price, currency,
billing basis, term dates, notice dates, deliverables, milestones,
acceptance criteria, assumptions, exclusions, signatories) with page refs,
and asks me to confirm each field before it's saved. Conflicts or gaps
block submission to the GM build.

## Acceptance tests (Given/When/Then)
- Given I upload `sample_sow.pdf`, when the extraction job completes, then
  the confirm screen shows each field with a page ref link and an
  "unconfirmed" chip.
- Given I click "Confirm" on each field, then the SOW status moves to
  `SOWDraft.confirmed` and the extracted fields are persisted immutably
  as `sow_version`.
- Given a field failed extraction (nil / conflicting values across pages),
  then the field is `disputed` and I must resolve manually before
  submission is allowed.
- Given the extraction proposes an `engagement_type`, then it's shown as
  a suggestion — I must accept or override.
- Given I re-upload a new file, then a new `sow_version` is created;
  the previous one stays for the audit history.
- Given I attempt to submit without confirming every field, then 422 with
  the specific field names.
- Given the file is > 25 MB, then 413.

## Data touched
- New tables: `sow` (one per opportunity), `sow_version` (immutable rows;
  file S3 key + file hash + extracted fields JSONB with page refs + confirmed_by).
- S3 bucket `officeapp-dev-sows-{account_id}` versioning + SSE-KMS.

## Roles allowed
- Upload: account owner or SystemAdmin.
- Confirm fields: account owner.
- Read: all governance roles.

## Out of scope
- Delivery Model Builder (Agent covers separately in the same sprint).
- Adversarial file scanning beyond MIME + size limits.

## Notes
- Blueprint §6.3.
- Extraction runs on Bedrock (Claude) for text-based PDFs; falls back to
  Textract for scanned PDFs. LLM output validated against a JSON schema
  before saved. Human confirmation is mandatory (rule 6).
- If Bedrock model access is not enabled in the dev account, the extract
  job returns a "manual entry required" state and the confirm screen
  becomes a manual data-entry form. Do not silently accept LLM output as
  confirmed.
