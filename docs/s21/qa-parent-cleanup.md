# Independent Parent Deletion and Trusted Cleanup QA

## Revision and Scope

- Reviewed production baseline: `69ae2b0ed23481108d17c10c3068b906a0804ca4`.
- Worktree/branch: `dealgate-s21-qa-parent-cleanup`, `s21/qa-parent-cleanup`.
- Contracts: S21-01 / CO-09 and `contracts.md` deletion/retention increment.
- Only additions: this report and `api/tests/test_s21_parent_cleanup_independent.py`.
- No implementation changes, weakened assertions, skips, retries, API calls, cloud calls, migrations, or shared database access.

## Reproduction

From this worktree:

```sh
env -u DEALGATE_POSTGRES_URL -u POSTGRES_URL PYTHONPATH=api \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest \
  api/tests/test_s21_parent_cleanup_independent.py \
  api/tests/test_s21_parent_deletion.py \
  api/tests/test_s21_trusted_cleanup.py \
  -o addopts='' -q -p no:cacheprovider --tb=short \
  --basetemp=/tmp/s21-qa-parent-fk
```

Result: **8 failed, 32 passed in 8.63s**, 40 cases, no skips or xfails.
Independent file: 27 cases, 19 passed / 8 failed. Existing parent and trusted-cleanup files: 13 passed.
`ruff check --no-cache api/tests/test_s21_parent_cleanup_independent.py`: passed.

The independent SQLite fixture explicitly enables and asserts foreign-key enforcement.
Rows are seeded in dependency order; no production function is mocked. The existing
tests retain their own unchanged session fixture. The storage fake is only an
external-boundary double, returns no object versions, and rejects delete calls.

## Findings

All node names below have prefix `api/tests/test_s21_parent_cleanup_independent.py::`.

1. **High: non-participant artifacts enter a trusted apply manifest.**
   `test_corrupted_or_untrusted_fixture_graph_is_not_a_cleanup_target[ungranted_agreement]`
   and `[ungranted_upload_job]` expect no target but receive the fixture client.
   A real Sales user outside the unchanged issued participant set owns the added
   agreement or pending upload. `fixture_cleanup.py:78` checks only SOW versions;
   `parent_deletion.py:109` and `:171` remove these other artifacts and enqueue
   their keys. Cleanup therefore does not establish ownership of its full target graph.
2. **High: opportunity deletion changes foreign-scope forecast rows.**
   `test_opportunity_delete_refuses_foreign_linked_forecast_before_mutation[tenant_id-foreign]`
   and `[environment-dev]` expect refusal before mutation; neither raises.
   `parent_deletion.py:128` detaches all linked plans without runtime-scope checks.
   Client deletion already refuses analogous foreign records at `:148`.
3. **Medium: malformed provenance and non-test participants are accepted.**
   `test_corrupted_or_untrusted_fixture_graph_is_not_a_cleanup_target[participant_mapping]`
   and `[real_uploader]` both receive a target. `fixture_cleanup.py:49` treats a
   mapping as a participant list; `:62` revalidates only the issuer, while `:80`
   tests uploader ID membership without checking the uploader's current test identity.
   These two cases deliberately corrupt local SQLite audit JSON. They establish
   fail-closed behavior gaps, not an exposed production audit-edit capability.
4. **Medium: mirrored source is incorrectly included in the manifest.**
   `test_corrupted_or_untrusted_fixture_graph_is_not_a_cleanup_target[mirrored_source]`
   selects a deal whose source is `hubspot` but whose HubSpot ID is NULL.
   `fixture_cleanup.py:76` omits the source check. Actual parent deletion correctly
   refuses it at `parent_deletion.py:91` / `:145`: this is a misleading/poisoning
   apply candidate, not proof that the mirrored parent can actually be deleted.
5. **Medium: malformed child ID escapes worker isolation.**
   `test_malformed_parent_dependency_is_visible_failure_not_worker_poison` raises
   `ValueError: badly formed hexadecimal UUID string` at `deletion_cleanup.py:50`.
   Parsing occurs outside the worker error handler, so the malformed job does not
   become visibly failed and the unrelated second job is not processed.

## Passing Controls and Limits

Controls cover active-run protection even with exact zero age; expired exact-run
selection; dry-read non-mutation; foreign tenant/environment, duplicate grant,
invalid correlation, missing owner, revoked issuer, and ungranted SOW uploader
refusal; invalid age configuration; three mirrored-parent variants; transaction
rollback after an earlier child removal; parent replay returning the original
pending job; and shared agreement-key preservation across clients.

Retention reads preserve literal financial amount `36924.125`, legacy hours
`3.25`, cost `162.50`, revenue `812.50`, frozen baseline, original source IDs,
and source-deleted state through the actual financial/project read services.

This is independent local service evidence, not S21-01/CO-09 acceptance. It does
not establish migrated PostgreSQL CHECKs, immutable-audit triggers, concurrent
locks/fences, versioned S3 behavior, HTTP permissions, browser behavior, or
scheduled activation safety. Parent/root retry API work remains lead-owned and
was not duplicated. Storage version removal and full signed/archived graphs
remain outside this bounded increment; no feature gate is closed here.
