# Independent Staffing Coverage QA

Baseline: `3d83bc993ff3003458ea827b03b82616ce3adf68`.
Branch: `s21/qa-coverage`. Budget: approximately 20 minutes of bounded authoring
and review plus serialized execution. Only this report and
`api/tests/test_s21_coverage_independent.py` changed. No production, schema or
existing-test edits; all red assertions remain unchanged.

## Method And Result

Thirteen independent cases use actual ORM/service paths with private in-memory
SQLite and foreign keys enabled. Existing canonical commercial/release fixture
builders supply setup only; separate plan/project owners, explicit staffing
mapping, managed supply, history and allocation go through actual services.
Expected headcounts/FTE are literal, not derived from production output.
Released package state is unit-fixture setup, not a signature/release proof.
There are no mocked feature responses, cloud calls, containers or browser runs.

An own APFS clone of the existing QA venv was created with `cp -cR`; dependency
files were not linked to another mutable worktree. The local Python executable
was used rather than a copied script with an old shebang. After the lead's
explicit runtime grant, from this worktree root:

```sh
env -u DEALGATE_POSTGRES_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api api/.venv/bin/python -m pytest api/tests/test_s21_coverage_independent.py -o addopts='' -q -p no:cacheprovider --tb=short --basetemp=/tmp/s21-qa-coverage-independent
```

Observed: **2 failed, 11 passed, 2 warnings in 43.47s**, exit 1. Zero skips or
xfails. Warnings are existing FastAPI `on_event` deprecations. Runtime was
released immediately after exit; no production correction or rerun occurred.

## Archive Recovery Defect

Persist a valid plan/project mapping, then archive the linked project. The
project remains an authorized retained business source with immutable provenance,
but the active-demand reader excludes it (`people_project_demand.py:86`). Coverage
still exists and makes allocation explicitly incomplete with
`staffing_coverage_stale` (`people_coverage.py:94-117`). Two recovery paths fail:

1. **History disappears from an authorized reviewer.** `list_coverage` builds
   its authorization population from active sources, then skips any root whose
   project publication is absent (`people_coverage.py:184-196`). The returned
   history has `current_version_id=None` and no items despite an existing
   immutable mapping. Expected: authorized history remains accessible, with
   stale state and the correct current mapping CAS.
2. **An explicit empty revision cannot clear the stale mapping.** `save_coverage`
   requires both endpoints in that same active population before distinguishing
   a removal from a new map (`people_coverage.py:134-138`). Clearing with correct
   mapping CAS and `mappings=[]` returns **404 Staffing source unavailable**.
   Expected: an authorized, audited empty revision can clear this obsolete map;
   active allocation then contains only the two original plan slots and is
   complete with known empty managed supply.

This violates the explicit clear-by-new-revision contract in
`docs/s21/contracts.md`'s final coverage sections. It is one recovery defect with
two independently reproduced symptoms. Supporting recovery must not relax
tenant/test authorization or permit new mapping against an archived source.

Exact red nodes:
- `api/tests/test_s21_coverage_independent.py::test_archived_project_mapping_history_remains_available_to_authorized_reviewer`
- `api/tests/test_s21_coverage_independent.py::test_empty_revision_can_clear_archived_project_mapping_and_restore_completeness`

## Passing Independent Controls

- **Sales global-before-filter concern did not reproduce.** A different owner's
  committed project competes with the Sales owner's tentative plan for one
  half-time person. The project consumes that capacity first. Without coverage,
  Sales sees two unfilled slots / one FTE gap in each of six months; with one
  explicitly covered slot, Sales sees one unfilled slot / 0.5 FTE gap. In both
  cases matched plan FTE is exactly zero, hidden project/person IDs are absent,
  and the result remains complete. `portfolio=False` reaches project sources
  before final visibility filtering in the reviewed baseline.
- Two roots cannot reuse one project slot on the same inclusive 15 November
  endpoint. Reuse beginning 16 November succeeds. The two plans plus full
  project then require exactly five people / 2.5 FTE throughout the tested term.
- A stale mapping CAS from a separate SQLAlchemy session returns 409 and leaves
  exactly one mapping version and one mapping audit. This is sequential stale
  writer proof, not simultaneous row-lock/concurrency proof on PostgreSQL.
- Request replay is actor-bound even when the second actor has Delivery write
  permission. Rejected replay appends no version.
- Republication marks existing coverage stale and restores four provisional
  source slots rather than silently rebinding it. Explicit review against the
  new source version restores three residual slots and changes the watermark.
- An empty revision still rejects foreign tenant, test-classification mismatch
  and Sales write-role attempts; rejected clears append no version.
- Deleting the plan cascades its mapping root/version while preserving the
  committed project and its demand publication.

## Boundaries

No code fix is approved by this report. True concurrent PostgreSQL locking,
deadlock behavior, storage cleanup, UI/browser recovery, sourcing/event refresh
and staging remain **missing** from this audit's proof. These scoped results do
not establish full FC-05/07 or T21/T22/T23 acceptance and do not replace the
lead's separate integration evidence. The unchanged red tests are ready for
lead-owned production correction and independent revalidation.
