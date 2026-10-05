# Observed Business Unit Readers

Scope: isolated `s21/crm-bu-readers`, base `d1936a7`. Owned changes are limited to
BU helpers/filter/facet/projection blocks in the pipeline service, the new BU
reader regression file and this report. Owner logic, shared API types, UI,
models, migrations and delivery publication/allocation remain untouched.

## Agreed Semantics

Only a configured enumeration mapping with a matching source object, current
mapping version and non-null record observation time can classify a value.
Nonempty values must belong to the configured option definitions. Unknown raw
values stay stored as evidence but do not become named BU filter buckets.
An explicitly observed null/empty value alone can match the missing-BU filter.
Unobserved, stale-version and unavailable mappings are not evidence of absence.
No fallback from an empty deal field to company values, or vice versa, may
override which object the mapping actually configures.

The same SQL population must drive rows, facets, client/deal lists, chips and
summary totals. Company facets cannot include unrelated/orphan clients or
clients excluded by owner, record authorization, closed-state or other axes.
JSON option membership must use structured PostgreSQL JSONB / SQLite JSON1
expressions, with both dialect compilations checked and no per-row requests.

The existing `business_unit: string | null` DTO cannot express all unavailable
reasons or supply separate value/label metadata. This increment preserves raw
known option IDs consistently, returning null for unusable values. Availability
reason rendering and option-label UI remain shared-contract integration work.

## Verification

Regression tests authored before production changes. They cover both source
objects, independent three-page membership and Decimal27 totals, confirmed
blanks, stale/unobserved/unknown options, unconfigured states, facet scope and
PostgreSQL/SQLite compilation. First bounded red run: **12 failed, 1 passed**.
The failures demonstrate valid BU selections returning no rows; missing-BU
selection incorrectly including all 21 open rows even when mapping metadata is
unavailable; empty scoped facets; and filters compiling to constant false due
to nonexistent columns. The unknown-raw-option test already passed and was
retained unchanged.

Implementation is authored with one shared effective BU SQL expression and
structured dialect-specific JSON table-valued membership. It adds no metadata
round-trip or per-record queries. Runtime is held again for independent QA and
lead browser work between runs. The subsequent authorized focused run passed
**29 tests**: 13 new BU cases, seven existing query-service/query-budget cases,
and nine existing population cases. No skips, xfails or retries; existing
assertions unchanged. Both dialect compilation checks passed. This is SQLite
execution and PostgreSQL compilation proof, not real PostgreSQL or staging
execution proof.

Exact command from this isolated tree:

```sh
env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-bu-readers/api:/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-bu-readers \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest \
  api/tests/test_s21_crm_bu_readers.py api/tests/test_hubspot_pipeline_query_service.py \
  api/tests/test_s21_pipeline_population.py -q -p no:cacheprovider --tb=short
```

Dependency executable reused read-only with current-tree imports, no bytecode
or pytest cache, and per-test in-memory SQLite. Runtime stopped after results.

## Remaining Integration

The service honors all supplied filters and trusted record scope for BU facets.
However, `api/app/routers/pipeline.py:880` currently supplies only trusted scope
and `PipelineFilters(include_closed=True)`, not active UI filter selections.
Router/UI wiring must be completed before claiming active-population facet
parity through the real application. Those paths are outside this ownership.
Real PostgreSQL JSONB execution, integrated API/UI availability reasons and
option labels, export journey and staging verification remain lead-owned.
