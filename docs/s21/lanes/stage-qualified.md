# Pipeline-Qualified Stage Metadata

Status: fixed and tested locally; not staging verified. Isolated branch
`s21/stage-qualified`, base `83f8bc7`. Only the stage service, new regression
file and this report changed. Models, migration, consumers and old tests remain
read-only; lead owns consumer activation and later composite-PK contraction.

## Provider Contract

HubSpot documents deal-stage probability as required and bounded from zero to
one: zero means Closed Lost and one means Closed Won. Display order is layout,
not outcome; labels are user-visible names. Its examples specify probability
without `isClosed`. Therefore valid probability determines classification, and
an optional supplied `isClosed` must agree. See the official
[HubSpot pipelines guide](https://developers.hubspot.com/docs/api-reference/legacy/crm/pipelines/guide)
(Manage pipelines / Create pipeline; Manage pipeline stages / Create stage),
read 2 October 2026. No live provider API was called.

## Implementation

- Frozen signature: `StageMap.resolve(stage_id, pipeline_id=None)`.
  Supplied pipeline IDs resolve only the exact pair, including refusing an
  empty or wrong pipeline. Omitted pipeline uses a compatibility lookup only
  when that stage ID is unique. `by_id` construction remains compatible;
  `by_pipeline_stage` is additive and explicitly represents qualified identity.
- Strict validation precedes all writes: response/results/stages shapes,
  identifiers, labels, display ordering and archived booleans; duplicate IDs;
  required finite probability in range; and optional closed-flag consistency.
  Invalid metadata raises a reason-bearing `ValueError`; classification remains
  unresolved instead of substituting open/lost/won defaults.
- While the database retains the global stage PK, duplicate incoming stage IDs
  or attempted rebinding to another pipeline fail the whole refresh before
  mutation. Existing bindings are locked/refreshed and never moved silently.
- Cached stages with missing or contradictory classification do not resolve.
  Valid archived/omitted cached stages preserve the existing historical lookup
  behavior. Labels and English keywords never determine outcome.
- Material pipeline/stage changes append before/after audit events in the same
  transaction, with null actor for source refresh. Unchanged refresh creates no
  duplicate configuration event. Rollback removes metadata and its audit.
- Additional storage guard: existing `NUMERIC(3,2)` cannot represent `0.999`
  without rounding it to a won outcome. Such metadata fails visibly with
  `stage_metadata_probability_exceeds_storage_precision`; a wider source
  probability column is required before accepting higher precision losslessly.

## Proof

Tests first: **27 failed, 1 passed**, exposing wrong-pipeline resolution API,
stage-only ambiguity, English label/order outcomes, malformed metadata accepted
as success, global-ID rebinding, guessed cached outcomes and absent audit.
An additional precision case was authored before implementation.
Final run: **58 passed, 1 inherited xfail** (29 new passed plus 29 existing
passed). The inherited S20 `test_worker_crash_resumes_from_cursor` explicitly
requires a running service and was not changed or treated as proof. No old
assertions were edited, no retries were used.

Exact command in the isolated tree, in a lead-approved runtime slot:

```sh
env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/Users/srikanthparimi/OfficeApp/dealgate-s21-stage-qualified/api:/Users/srikanthparimi/OfficeApp/dealgate-s21-stage-qualified \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest \
  api/tests/test_s21_stage_qualified.py api/tests/test_hubspot_stage_mirror.py \
  api/tests/test_hubspot_backfill.py api/tests/test_hubspot_backfill_scan_generation.py \
  api/tests/test_s20_sync_edge_cases.py -q -p no:cacheprovider --tb=short
```

Dependency executable was reused read-only, with current-tree imports,
per-test private in-memory SQLite, no bytecode/cache or shared DB writes.
Real PostgreSQL races, qualified consumer activation, composite-key contraction
and integrated worker/staging journeys remain lead-owned verification gates.
