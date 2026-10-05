# Same-Document Extraction Replay

Isolated branch `s21/extraction-overrides`, baseline `0dd0432`. Read the lead's preimplementation contract `4f2d3ea`, final Same-Document Extraction Replay section, directly from integration. Owned only replay/merge code in `services/sow_extract.py`, the reextract endpoint gate/docstring in `routers/sow.py`, dedicated tests and this report. No schema, upload-pipeline, provider adapter, shared tests or deployment edits.

## Implemented Behavior

Preserve explicitly confirmed field envelopes byte-for-value, including accepted unchanged extracted fields; manual/default provenance alone is not evidence of human confirmation. Same-version replay requires matching actual bytes/SHA256 and a mutable, never-submitted source. Any existing approval package, version-level confirmation, executed/superseded/discarded source must refuse replay. Changed source bytes are a409, never an implicit correction transfer.

New provider candidates remain strictly validated. A conflicting valid candidate stays separate from protected fields and yields visible manual-required/conflict state. A failed attempt keeps prior confirmed evidence without claiming extraction complete. Reuse existing provenance and audit, not a parallel extraction or override service. Full source-change proposal/review, held-out corpus and FC-09/T24 acceptance remain outside this bounded increment.

## Test-First State

Sixteen focused tests were authored before production edits. They use real synthetic DOCX bytes, actual SQL persistence and confirm_field auditing, and the real reextract HTTP handler. Provider/storage boundaries are explicitly local test doubles, not integrated staging evidence. Cases cover differing successful candidates, failed retries, identical accepted values, unconfirmed legacy manual defaults, source-byte mismatch, nine immutable states and HTTP409/200 behavior.

Initial red: **14 failed, 2 passed**, exit1, no fixture setup errors. It reproduced value/provenance/status loss, silent source changes, nine immutable-source mutations and incorrect HTTP200. After the scoped correction: **53 passed**, exit0 (16 new,37 unchanged extraction/OCR/confirmation/scoping/staffing/defaulted regressions), no skips/xfails/retries. No old test assertions or fixture hashes changed. No dummy-hash fixture gaps were found in this selected regression.

`run_extract` now takes parent-first locks and reloads the source version before checking existing confirmation/lifecycle/approval-package history. Same-version replay compares actual bytes to the stored hash; the HTTP reextract route explicitly sets replay even for a pending version. Initial internal extraction retains its existing pending/test-empty-byte contract, not a bypass for this replay endpoint.

Successful candidates merge with exact deep-copied confirmed envelopes. Changed candidates appear under `extracted_fields.metadata.reextract_conflicts`, while status/error and `sow.extract_failed` report the conflict. No conflicting candidate is auto-confirmed. Failed provider/schema/OCR attempts preserve existing fields/evidence and retain failed status. Audit payloads record preserved field names and source hash. Existing confirmed-type state remains intact. This is not a versioned extraction-attempt history or a complete conflict-editor implementation; those remain integration/corpus work.

Private dependencies prepared with APFS clone:

```sh
cp -cR /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv /Users/srikanthparimi/OfficeApp/dealgate-s21-extraction-overrides/api/.venv
```

Clone completed exit0. Tests invoked this tree's `api/.venv/bin/python`, current-tree-only PYTHONPATH, bytecode disabled and pytest cache disabled, isolated SQLite only. No live provider/cloud calls or shared runtime. Lead explicitly granted the sole runtime slot after its browser finished; slot released after all processes completed.

Exact final command from the isolated worktree (red used only the first test file):

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/srikanthparimi/OfficeApp/dealgate-s21-extraction-overrides/api:/Users/srikanthparimi/OfficeApp/dealgate-s21-extraction-overrides api/.venv/bin/python -m pytest api/tests/test_s21_extraction_overrides.py api/tests/test_sow_extract.py api/tests/test_textract_fallback.py api/tests/test_sow_confirmation.py api/tests/test_sow_id_scoping.py api/tests/test_staffing_byte_identity.py api/tests/test_defaulted_grid_regression.py -q -p no:cacheprovider --tb=short
```

Remaining verification: PostgreSQL contention with approval/source deletion, real storage/provider and integrated UI review, fresh-source revision handling, main upload/OCR adapter alignment and independent held-out seven-profile evaluation. No whole FC-09/T24 or staging acceptance claim.
