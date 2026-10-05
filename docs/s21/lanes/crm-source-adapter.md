# CRM Source Adapter Increment

Status: local verification only; no staging claim. Isolated `s21/crm-metadata`
worktree, following metadata commits `09e4e6a` and `889cf66` (lead integrated
those as `c08659d` and `28775b2`). Model/schema and metadata service are read-only.

## Changes

- Deal and company observations persist authoritative external owner IDs and
  observation times independently of legacy local `owner_id`. No source ID is
  synthesized from a login, leader or unassigned sentinel. Legacy local user
  resolution/task assignment remains compatible and is not CRM identity.
- A frozen configured BU selection carries property name, object and version
  across provider fetches. Only that property is added to deal, paged-deal or
  company requests. Before storing values the transaction locks/rechecks the
  mapping; changed/unavailable selections cannot stamp a different version.
- A fetched empty/null field is an observed empty value; an omitted field is
  not observed. Unknown option strings remain exact raw source values, not
  invented labels. Source value, mapping version and observed time are stored
  together for the correct source object only.
- Existing deal/company rows are locked and compared against source modified
  time before writes. Older fetches, or unversioned fetches for an already
  versioned record, cannot overwrite it. Missing fields preserve existing
  facts; explicit null clears nullable currency/activity and other supplied
  fields. Modified time is no longer manufactured into last activity.
- Company writes wrap the existing shared upsert without changing that shared
  service. A partial company response preserves an unfetched name. Source facts
  and source version appear in the existing opportunity audit or a company
  source-observation audit in the same transaction.
- Backfill changes are limited to property selection/context passing. Scan,
  archive, lease, cursor and generation protocols are untouched and lead-owned.

## Evidence

Initial new tests: **14 failed, 5 passed** before implementation. Failures exposed
missing external owner/BU observations, fabricated activity, stale overwrite,
missing property selection, company facts and mapping context. First combined
run: **54 passed** (19 new plus 35 existing), no skips/retries. Three additional
tests then gave **1 failed, 2 passed**: a partial company response replaced a
real name with `Unnamed HubSpot company`. The two passing tests exercised
source/audit rollback and the real paged backfill path with provider transport
fixtures, SQLAlchemy writes and metadata discovery, not mocked feature APIs.
After the partial-name fix, the combined focused run passed **57 tests**
(22 new plus 35 existing), no skips/retries.

Static follow-up identified an ORM identity-cache hazard despite row locking.
Two regressions advanced the persisted source version behind the cached ORM
instance without synchronizing it; **both failed**, overwriting the newer
source owner with the stale fetch. Locked source reads now use
`populate_existing=True` before mutation, so version comparison reads the
database row rather than a previously loaded instance. Production source
mutation occurs only after this acquisition; callers must not pre-mutate the
source row, since ordinary session autoflush happens before ORM queries.
The first combined refresh run had **55 passed, 4 failed**: these four own-test
assertions assumed pre-roundtrip Decimal string formatting and SQLite retaining
timezone info. They now assert equal Decimal values and equal normalized UTC
instants, preserving the business assertions. Existing test assertions remain
unchanged; the identity-cache regressions assert the actual persisted owner.
Final focused run: **59 passed** (24 new plus 35 existing), no skips/retries.

Exact focused command (private in-memory SQLite, read-only dependency reuse):

```sh
env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-metadata/api:/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-metadata \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest \
  api/tests/test_s21_source_adapter.py api/tests/test_hubspot_intake.py \
  api/tests/test_hubspot_backfill.py api/tests/test_hubspot_stage_mirror.py \
  api/tests/test_hubspot_backfill_scan_generation.py -q -p no:cacheprovider --tb=short
```

No existing test assertion was modified. No live provider, shared DB, worker
runtime, cloud or browser operation was used; tests ran only in lead-approved
bounded slots. Production source owner/BU visibility and consumer semantics
still need integration and staging proof.

## Remaining Dependencies

- Pipeline/UI must use external IDs plus observed state, including unavailable
  owner metadata and BU availability/version. Legacy `owner_id` remains separate.
- Primary-company association ordering and webhook pipeline-stage compatibility
  remain pre-existing gaps outside this property-observation increment.
- Authorized CAS metadata selection, owner mirror freshness/error propagation,
  atomic backfill lease/cursor protocol and live provider validation remain open.
- Missing/invalid source modified time on an already versioned row fails closed;
  initial unversioned fixtures can be observed but are not proof of ordering.
  Source-time concurrency uses row locks; PostgreSQL race proof remains required.
- No S21/Forecast requirement or acceptance scenario is declared complete solely
  by these focused tests.
