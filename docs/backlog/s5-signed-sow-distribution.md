# S5 E8 — Signed SOW verify + diff + distribution

## User story
When Sales uploads the executed SOW, the system re-extracts key terms
(price, dates, scope) and diffs them against the approved package. If any
term drifts, release is blocked. If terms match, the signed SOW is
distributed by email to the account owner, Delivery owner, Finance and
leadership; a kickoff task is filed; a renewal record is created for T-2mo
before the term end.

## Acceptance tests
- Given a package is `ready_to_sign`, when Sales uploads a signed pdf and
  calls `POST /signed-sow/{package_id}/verify`, then extraction runs and a
  diff is returned. On match → status `verified`. On mismatch → status
  `blocked` with the diff.
- Given `blocked`, Sales cannot release; the block persists.
- Given `verified`, calling `POST /signed-sow/{package_id}/release`
  distributes the file via SES, files kickoff + billing-setup + renewal
  records, moves package to `released`, and audits `package.released`.
- Only the account owner may verify+release. SystemAdmin can too.
- Re-uploading a different signed pdf voids the previous verification;
  audit `signed_sow.replaced`.
- Distribution notification list configurable via `NotificationSetting`
  category `signed_sow_released`.

## Data
- New: `signed_sow_upload` (id, package_id FK, file_s3_key, file_hash,
  uploaded_by, uploaded_at, verify_status, diff_json, verified_at,
  released_at nullable).
- New: `renewal` (id, opportunity_id FK, term_end date, trigger_date date,
  status VARCHAR (open|closed|extended|churn), outcome_summary text,
  replacement_sow_version_id nullable).

## Roles
- Read: all governance roles.
- Upload+verify+release: account owner or SystemAdmin.

## Notes
- Blueprint §6.7.
- Uses Bedrock extraction shared with SOW upload (same schema).
