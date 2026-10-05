# Independent Project Source Scope QA

Baseline: `68899157463a17759080390df71abbed4bcedeed`.
Branch: `s21/qa-project-scope`. Budget: approximately 15 minutes of authoring and
review plus the lead-authorized serialized focused run. Only this report and
`api/tests/test_s21_project_scope_independent.py` changed. Production and existing
tests remain read-only. All nine red assertions are preserved unchanged.

## Method And Result

Fifteen independent cases use actual ORM objects with SQLite foreign keys ON,
`save_commercial_model`, `create_or_link`, `capture_project_scope`,
`project_scope_allowed`, `create_fixture`, `request_sow_deletion`,
`request_client_deletion` and `list_projects`. No feature response is mocked.
The existing canonical `wire` helper supplies only commercial fixture inputs;
expected authorization decisions and retained identifiers are independently
specified. A released ApprovalPackage is unit-fixture setup, not proof of the
signature/release workflow. Empty owned storage keys mean no external storage
call is needed; no cloud or database server is contacted.

Run from this worktree root with the existing QA venv executable read-only:

```sh
env -u DEALGATE_POSTGRES_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest api/tests/test_s21_project_scope_independent.py -o addopts='' -q -p no:cacheprovider --tb=short --basetemp=/tmp/s21-qa-project-scope-independent
```

Observed: **9 failed, 6 passed, 2 warnings in 17.78s**, exit 1. Zero skips/xfails.
Warnings are existing FastAPI `on_event` deprecations. Runtime was released
immediately at exit. No production fix or assertion relaxation was made.

## Findings

### 1. Retained Projects Reader Bypasses Runtime Scope

After actual SOW deletion, change `DEALGATE_TENANT_ID` to `foreign`.
`project_scope_allowed` correctly returns False, but `list_projects` still
returns the retained project, including its frozen commercial baseline to the
Delivery actor. The retained branch queries all detached projects and uses
account/test checks rather than the new runtime-aware helper
(`api/app/services/projects.py:126-146`). This is a real read-boundary gap, not
merely acceptance of malformed helper input. The helper alone does not protect
its consumers.

Red node: `test_real_deleted_project_read_does_not_bypass_foreign_runtime_scope`.

### 2. Legitimate Owner Reassignment Invalidates Retained Business Scope

Capture a real canonical project under owner A, persist a legitimate new real
deal owner B, then call actual SOW deletion. The baseline remains correctly
frozen under A, while deletion stores the current owner B in
`retained_source.owner_id` (`api/app/services/deletion.py:617-622`). The helper's
unconditional comparison to the frozen owner (`project_source.py:158-159`)
returns False even for a real Delivery actor. That drops a legitimate retained
source without any change to its commercial evidence or tenant.

Expected: original commercial ownership and current portfolio ownership remain
distinguishable; changing the latter must not invalidate the former. This does
not relax fixture issuer/owner binding: trusted test grants still bind their
original authoritative issuer and cannot follow arbitrary owner reassignment.

Red node: `test_real_owner_reassignment_before_deletion_does_not_destroy_retained_authority`.

### 3. NULL Package FK Can Lose All Detachment Evidence

The main lineage loop covers opportunity, SOW version, GM and client, not the
package (`project_source.py:147-157`). Package is checked only when its FK or
retained metadata is present (`:160-163`). Both cases incorrectly return True:
live project package FK set to NULL without a deletion marker; and actual
SOW-deleted project whose retained `package_id` is removed. Expected: missing
live or detached package provenance fails closed, like the other source links.

Red nodes:
- `test_missing_package_lineage_does_not_authorize_live_or_retained_source[False]`
- `test_missing_package_lineage_does_not_authorize_live_or_retained_source[True]`

### 4. Contradictory Retained Test Classification Is Ignored

Actual deletion writes `retained_source.test_fixture`. Flipping that field from
False to True on a real retained project, or True to False on a service-issued
fixture, does not change authorization. `project_source.py:146-181` compares
several retained fields but not that classification. The recorded grant remains
authoritative, but a conflicting persisted classification must be rejected,
not accepted by one consumer while another trusts the opposite flag. This is
a corruption/fail-closed test, not a demonstrated grant-based identity crossover.

Red nodes:
- `test_retained_fixture_classification_conflict_is_fail_closed[False]`
- `test_retained_fixture_classification_conflict_is_fail_closed[True]`

### 5. Explicit Change To CRM Source Provenance Is Not Rechecked

The fixture is issued through actual `create_fixture`, which creates a local
`source="sow_upload"` deal (`test_fixtures.py:53-60`), not the old test helper's
default-source row. Change that explicit source to `hubspot` while external IDs
remain absent. Capture still succeeds (`project_source.py:109-118`), and a
previously captured fixture remains readable after the same source change
(`:173-180`). Expected: this contradictory authoritative fixture source is
rejected pending reconciliation. The tests do not claim a legacy default of
`hubspot` alone establishes that an external CRM record exists.

Red nodes:
- `test_capture_rejects_mirror_source_even_without_external_ids`
- `test_surviving_fixture_parent_cannot_invalidate_grant_and_stay_authorized[mirror_source]`

### 6. Archived Surviving Fixture Account Still Grants Access

After real SOW deletion, archive the still-existing fixture account. The helper
returns True: it checks the surviving client's external ID but not archive state
(`project_source.py:173-176`). Authoritative `account_scope` rejects archived
accounts (`test_fixtures.py:113-115`). Retention can remove parents, but it should
not bypass invalidation on a surviving fixture parent.

Red node: `test_surviving_fixture_parent_cannot_invalidate_grant_and_stay_authorized[archived_account]`.

All suffixes above use prefix
`api/tests/test_s21_project_scope_independent.py::`.

## Passing Controls

Actual deletion-created `retained_source` is compatible with the helper for both
real and service-issued records when provenance is unchanged. The exact original
client/opportunity/SOW-version/GM/package IDs survive. SOW deletion detaches its
three source FKs; subsequent client deletion detaches account/opportunity FKs;
the project survives with an unchanged baseline and remains authorized in its
original scope. A foreign tenant is rejected by the helper in both cases.

After real source and parent deletion, expired issuance, forged owner or changed
run/correlation evidence denies the fixture actor and does not fall back to an
ordinary real administrator. Cost-free canonical staffing projection omits the
commercial values, and HR live/retained Projects reads do not return the frozen
financial baseline. These controls do not prove a project-demand consumer that
has not yet been integrated.

## Acceptance Boundary

Connected project-demand publication, global allocation, sourcing/history,
effective amendments, PostgreSQL locking, real storage and staging remain
**missing** from this audit's proof. No full S21-01, CO-09, FC-07, T22 or T23
acceptance is claimed. Production fixes and integration belong to the lead;
these unchanged cases require independent revalidation afterward.
