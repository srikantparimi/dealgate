# Retained Project Source Scope

## Ownership And Contract

Isolated branch `s21/project-source-scope`, baseline `2198f89` on `8bc9d7d` (verified from this tree, rather than assuming the reported cherry-pick hash). Owned only new `project_source.py`, create-or-link scope capture in `project_lifecycle.py`, dedicated tests, and this report. The existing canonical deep-copy fix is untouched. No models, migrations, routers, deletion, publication, financial projection, infrastructure or other trees were edited.

The lead approved the following immutable `baseline_snapshot_json.source_scope` shape:

```text
schema_version: project-source-v1
tenant_id, environment: canonical commercial snapshot scope
opportunity_id, sow_id, sow_version_id, gm_model_id: exact frozen UUID strings
account_id, owner_id: original account and deal owner UUID strings
source_hash: SHA256 of canonical JSON commercial_inputs + commercial_snapshot
fixture_grant_id: authoritative AuditEvent UUID, or null for proven non-fixture
```

`capture_project_scope(session, *, opportunity, sow_version, gm_model)` returns that object or `None` for a valid legacy source without canonical scope. It rejects malformed canonical evidence, component/schedule disagreement, mismatched GM/SOW/deal lineage, foreign runtime, invalid or ambiguous fixture issuance, and test-owned records lacking issuance. `create_or_link` captures only on creation and converts provenance conflicts to HTTP409. Existing baseline replay is never rewritten or adopted into a different runtime.

`project_scope_allowed(session, *, actor, project)` is scope authorization only, not a role or portfolio policy. It verifies canonical runtime/hash/lineage and present or retained original IDs. Fixture authorization revalidates the exact append-only client issuance, original owner/deal/account, issuer's current test-administrator status, explicit participant membership, aware expiry and runtime even when live source links have been detached. A null grant does not authorize ordinary scope if any authoritative fixture issuance exists for that account. A test flag is never sufficient. It creates no parent rows and returns no financial projection.

## Verification

Initial red: 21 failed, exit1. Twenty cases establish missing helper contracts (module absent); the existing real `create_or_link` accepted foreign canonical runtime without the required HTTP409. No fixture setup crashes. Three additional cases cover post-release expiry via a clock boundary, real/test isolation and a test owner without issuance. These added cases were not included in the initial red count.

Static review added three further live-parent contamination cases. First implementation run: 24 passed, 3 failed, exit1. Those failures reproduced fixture authorization surviving company/deal mirroring or an owner change. Read-time checks now refuse those surviving-parent conflicts while allowing genuinely absent detached parents.

Final combined run: **48 passed, 5 inherited xfailed, exit0**, 53 collected. All27 new source-scope cases, canonical baseline8 and existing release-gate13 passed. The five excluded cases are the unchanged explicit `pytest.mark.xfail` cases in `test_s20_release_authorization.py` (reasons refer to W7); they are not evidence of passed S20 acceptance. No retries, skips, weakened existing assertions or new expected-failure markers. `git diff --check` passed. The runtime slot was released only after all test processes exited.

Tests seed real canonical commercial persistence and invoke actual release-baseline creation against isolated SQLite. Approval package setup supplies source context, not a fully verified approval/signature journey. Detachment in these unit tests simulates the persisted FK/retained-ID shape; deletion/publication and PostgreSQL concurrency remain integration proof, not claims from this file.

Runtime provenance: read-only `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH` set only to this worktree's `api` and root, pytest cache disabled. No shared database or cloud calls.

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/srikanthparimi/OfficeApp/dealgate-s21-project-source-scope/api:/Users/srikanthparimi/OfficeApp/dealgate-s21-project-source-scope /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest api/tests/test_s21_project_source_scope.py api/tests/test_s21_project_commercial_baseline.py api/tests/test_release_gate.py api/tests/test_s20_release_authorization.py -q -p no:cacheprovider --tb=short
```

## Integration Dependencies

Lead owns cost-free People projection, allocation/publication and surviving conversion lineage, actual deletion and detached-parent journeys, API readers, schema ordering, deployments and staging proof. Missing legacy provenance remains an explicit unresolved source, not complete zero demand. No S21/Forecast completion or staging claim is established by this bounded increment.
