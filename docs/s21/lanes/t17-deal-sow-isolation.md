# T17 Deal And SOW Fixture Isolation

## Scope

Implementation lane on `s21/t17-deal-sow-isolation`, based on
`befea4b1682b6745ac26decbba830fb176bce4c1`. This is not independent approval of
the implementation and does not close T17, DG05, or staging acceptance.
The preserved OCR/inventory branches were not modified.

Owned production files are `routers/deals.py`, `routers/sow.py`, and, by the
lead's explicit extension, only the history reader in `routers/sows_staffing.py`.
No service, schema, commercial calculation, UI, or provider code was changed.

## Repair

- Resolve the canonical persisted actor before ownership checks, including an
  invited profile whose token subject differs from its existing user ID. Commit
  identity synchronization before business reads/locks, as in the client guard.
- Apply authoritative `account_scope` and `user_allowed`, including the exact
  issued opportunity, before deal pagination and totals, detail, and mutation.
- Guard SOW current/version/download-URL responses, confirmation, conflict
  review, and owned legacy writes. `reviewer_scope` also validates fixture
  document uploader provenance before file references or signed URLs are exposed.
- Guard history before loading it; filter each DTO through its underlying ORM
  version's authoritative reviewer scope. Ordinary governance SOW readers retain
  their existing access even when they do not own the opportunity.
- Deal tasks require an unambiguous `ApprovalAssignment -> ApprovalPackage`
  relationship to that exact opportunity and `allowed_for_package`. Shared owner
  identity is not sufficient. Unattributed legacy tasks remain in My Work; this
  patch does not infer legacy deal lineage from subject text or change My Work.

## Evidence

Tests use actual SQLite ORM rows and ASGI routes, server-issued fixture grants,
and a deterministic S3 provider stub. No provider calls, shared DB, migration,
browser, or staging operation was performed.

Baseline run `9284`: 14 failed, 1 passed; no setup errors, skips, or xfails.
Failures cover unauthorized populations/totals, expired/foreign/forged grants,
canonical identity alias, same-owner unrelated task attribution, untrusted
document uploader, and confirmation disclosure. The existing ordinary non-owner
Sales SOW-read policy already passed and its assertion remains unchanged.

First repair run `70109`: six new-test failures from passing a history DTO to
`reviewer_scope`, which expects `SowVersion`. Existing deal and extraction tests
passed. The production guard was corrected; assertions were not weakened.

Final run `17414`: 44 passed, no skips or xfails, 32.31 seconds. This is the 15
new cases plus 29 existing deal/extraction regressions. Six existing deprecation
warnings were emitted. JUnit: `/tmp/s21-deal-sow-green2-befea4b.xml`.
The new assertions stayed unchanged across red and green runs. Ruff initially
flagged six one-line test-fixture conditionals; those were expanded without
behavior changes. Final Ruff check of all four Python files passed; `git diff
--check` also passed.

Reproduction from this worktree's `api` directory, using the integration
interpreter read-only:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-forecast/api/.venv/bin/python \
  -m pytest tests/test_s21_deal_sow_fixture_access.py tests/test_deals.py \
  tests/test_sow_extract.py -o addopts= -q -p no:cacheprovider \
  --basetemp=/tmp/s21-deal-sow-verification
```

## Uncovered Boundaries

- Only the history reader was authorized for edits in `sows_staffing.py`.
  Revision upload, resources/staffing, supersede/discard/delete and draft-list
  routes there are not established safe by this patch. Upload-job, delivery-model,
  approval, project, and other routers are likewise not certified here.
- No PostgreSQL simultaneous-request, row-lock, or browser proof was run.
- Legacy task audit lineage is not reconstructed; only authoritative assignment
  linkage is projected into deal detail. My Work records are preserved.
- Agreement storage/replacement/deletion is the lead's separate ownership.
