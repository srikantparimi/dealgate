# Independent Deletion Review

Source: `9bc8ed758a9eff5b167e9dd13922921501640b7c`, branch `s21/qa-deletion`.
Window: 2 October 2026, 04:56 UTC; bounded 15-minute independent review.
Owned additions only: this report and `api/tests/test_s21_deletion_independent.py`.
No application changes, shared runtime, cloud calls, migrations or subagents.

## Result

Combined targeted run: **24 cases, 18 passed, 6 failed, 0 skipped, 0 xfailed**.
Independent additions: 16 cases, 10 passed, 6 failed. Existing deletion-job and
sibling-boundary tests: 8 passed. Ruff on the added test file passed.
All six failing assertions remain enabled and unchanged after reproduction.
Final rerun: 6 failed, 18 passed in 9.96 seconds. Financial fixtures use the
persisted `committed` batch status and `billed_revenue` measure.

```sh
env -u DEALGATE_POSTGRES_URL PYTHONPATH=api \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest \
  api/tests/test_s21_deletion_independent.py \
  api/tests/test_s21_deletion_jobs.py \
  api/tests/test_s21_deletion_boundaries.py \
  -q -rA -p no:cacheprovider --tb=short \
  --basetemp=/tmp/s21-qa-deletion-combined
```

Run from `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-deletion`.
The prior QA venv is used read-only; imports resolve to this worktree's `api`.

## Findings

1. **High: cleanup destroys an exact key claimed after the request.**
   `api/app/services/deletion_cleanup.py:51` deletes the persisted manifest
   without querying surviving references again. The test queues deletion,
   commits a new sibling SOW using `del/one.pdf`, then runs the real worker
   with an injected storage boundary. It deletes both the version and marker
   even though that SOW now owns the object.
   Node: `test_cleanup_rechecks_key_claimed_by_surviving_sow_after_request`.

2. **High: parent agreement object is not protected when buckets overlap.**
   `api/app/services/deletion.py:583` collects only other SOW/signed-upload
   references. With both supported bucket settings equal and an MSA referencing
   the same key, its database row survives but its object is queued for deletion.
   This is specifically an exact bucket/key collision, not a prefix collision.
   Node: `test_parent_agreement_same_bucket_key_is_not_queued`.

3. **High: stale bound-upload callback bypasses the fence.**
   `api/app/services/sow_upload_job_service.py:514` accepts a preloaded upload
   whose linked version and job were deleted. Unlike `resume_after_pick`, it
   does not check the job fence; `:601` onward can create another SOW/version.
   An invalid PDF exercises local extraction failure without any provider call.
   Expected deleted-source rejection is absent.
   Node: `test_stale_bound_upload_cannot_recreate_deleted_sow`.

4. **High: live-source tenant/environment mismatch is ignored.**
   `api/app/services/deletion.py:565` loads the SOW by UUID and `:575` gathers its
   GMs without validating their persisted `commercial_snapshot` scope. A GM
   explicitly marked for another tenant or environment is accepted for deletion
   and recorded under the caller runtime's fence/job scope. This is a direct
   service boundary finding, not a claim about the unactivated HTTP route.
   Nodes: `test_mismatched_commercial_source_is_not_deleted[tenant_id-other-tenant]`
   and `test_mismatched_commercial_source_is_not_deleted[environment-staging]`.

5. **Medium: default upload bucket is lost from the cleanup manifest.**
   `api/app/services/deletion.py:585` records an empty bucket when `SOW_BUCKET`
   is absent, although `api/app/integrations/s3_sow.py:66` supports the
   `officeapp-dev-sows-{AWS_ACCOUNT_ID}` fallback. Such jobs cannot remove their
   uploaded object: `deletion_cleanup.py:14` rejects the empty bucket.
   Node: `test_supported_default_upload_bucket_is_recorded_for_cleanup`.

All node names above are prefixed by
`api/tests/test_s21_deletion_independent.py::`.

## Passing Boundaries and Limits

Independent checks preserve preexisting shared-key siblings, parent agreements
on distinct keys, parent actions, project baseline/original IDs and both actuals
models across archived, rejected, ready-to-sign and released package fixtures.
Legacy resource references are detached with original IDs retained; literal
hours, cost, revenue and invoice values survive. Exact-key cleanup removes
versions/markers without prefix-neighbour loss; repeat processing has no new
external effect. Fences distinguish tenant/environment, a foreign-tenant job is
not processed, and storage errors cannot be reported as success.

Fixtures use ORM setup, not a real review/signature journey. The reusable seed
only constructs the graph; monetary expectations are independent Decimal
literals. Existing SQLite `create_all` fixtures do not enable FK enforcement:
these tests do not prove PostgreSQL cascades, advisory locks, concurrent commit
ordering or migration parity. The storage double tests worker intent, not S3.

S21-01: **missing**, six red local assertions across five findings; public
activation, browser flow, provider cancellation and real concurrent workers are
outside this review. CO-09: **missing**, no scheduled-client-cleanup, trusted-run
age/ownership sweep, client-delete bypass or teardown leak-gate acceptance was
performed. T01/T28/T32/T45 are not closed by this unit evidence. Lead integration,
production fixes and independent rerun remain required; this worker does not
approve its own fixes.
