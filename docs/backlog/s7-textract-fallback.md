# S7 — Textract fallback for scanned SOW PDFs + drop Teams/Slack UI

## User story A: Textract fallback
As the account owner, when I upload a scanned/image PDF (no text layer),
the extraction pipeline runs AWS Textract first to OCR the pages, then
passes the recovered text to Bedrock for field extraction. Prevents
"ManualRequired" for scans that could have been OCR'd.

## Acceptance A
- `api/app/integrations/textract.py`: `extract_text(pdf_bytes) -> str`
  using `AnalyzeDocument` (or `StartDocumentAnalysis` for > 10 pages).
- `sow_extract.run_extract` detects "text density < N chars/page" from
  the raw pdf parse, calls Textract, then feeds the recovered text to
  Bedrock. On Textract failure → `ManualRequired` (never fabricate).
- Textract stub for tests returns canned text.
- Cost note in docstring: Textract charges per page.
- Test: scanned PDF fixture (a page with an image) → Textract stub called
  → Bedrock stub receives OCR text → extracted fields populated.

## User story B: Drop Teams / Slack UI
Per user directive: remove the channel toggles from the notification
settings page + hide any Teams/Slack references in the UI. Keep the
enum values in the database so existing rows don't error; mark
deprecated in code.

## Acceptance B
- `web/src/pages/NotificationSettings.tsx`: remove the `teams` and
  `slack` columns from the settings matrix.
- `api/app/services/notifications.py`: `NOTIFICATION_CHANNELS` keeps
  `teams` + `slack` (schema-compat) but a new `ACTIVE_CHANNELS = {"email",
  "inapp"}` is what the settings API + queue_notification consult.
  Queue skips inactive channels with `suppressed` + reason `"channel disabled"`.
- Test: PATCH to enable `teams` returns 422 "channel disabled"; existing
  DB rows with `teams=true` still queue → suppressed (no crash).

## Notes
- Blueprint §11 called Teams/Slack a config-toggle; user has dropped it.
