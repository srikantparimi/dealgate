# CRM Facet Wiring

## Scope

- Branch `s21/crm-facet-wiring`, isolated worktree `dealgate-s21-crm-facet-wiring`, baseline `494ae2e`.
- Owned facet endpoint plumbing in `api/app/routers/pipeline.py`, facet request/query plumbing in `web/src/pages/v2/Pipeline.tsx`, dedicated backend/frontend tests, and this report.
- Lead explicitly extended ownership to only `getPipelineFacets` in `web/src/api/client.ts`, using the existing `pipelineParams` serializer. Client URL filter preservation in Pipeline was also approved.
- No schema, source service, deployment, shared database, or other worktree edits.

## Changes

The facet endpoint now parses the same axes as rows and summary, resolves group/watch intersections, and applies trusted account scope before querying. Invalid query values receive the same validation as row requests. Default facets describe the default open population; explicit closed filters remain supported.

Pipeline requests facets with its current normalized filters alongside rows and summary. The existing request-version fence protects all returned population data, including facets, against out-of-order responses. Client URL filters now survive both parsing and subsequent filter changes. Empty BU facets say no matching BU rather than asserting that portal metadata is unavailable.

## Evidence

- Backend red: 15 failed, 1 passed. Failures reproduced ignored axes, leaking group/watch facets, and ignored invalid parameters. Reader authorization already passed.
- Frontend initial fixture setup omitted required summary counters and caused two unhandled rendering errors. This was corrected in the new test fixture before the meaningful red run; those errors are not counted as product regressions.
- Valid frontend red: 3 failed, no unhandled errors, demonstrating missing request filters, mount-only facets, and absent shared-client serialization.
- Backend green: 38 passed, exit 0 (new facet 16, existing BU reader 13, existing population 9).
- Frontend green: 5 passed, exit 0, 24.55 seconds (new facet 3, existing population 2). Only existing React Router future-flag warnings.
- No existing assertions changed, no retries or new exclusions. Tests do not establish staging or complete requirement coverage.

Backend command, from the isolated worktree:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-facet-wiring/api:/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-facet-wiring /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest api/tests/test_s21_facet_filters.py api/tests/test_s21_crm_bu_readers.py api/tests/test_s21_pipeline_population.py -q -p no:cacheprovider --tb=short
```

The executable reuses QA dependencies read-only; imports resolve to this worktree, bytecode/cache writing is disabled, and tests use isolated SQLite state. Backend tests mount the real router and query the database; only authentication/session dependency boundaries are supplied locally.

Frontend command, from this worktree's `web` directory:

```sh
./node_modules/.bin/vitest run src/__tests__/v2/S21PipelineFacets.test.tsx src/__tests__/v2/S21PipelinePopulation.test.tsx --maxWorkers=1 --minWorkers=1
```

Dependencies were privately APFS-cloned using `cp -cR /Users/srikanthparimi/OfficeApp/dealgate-s21-forecast/web/node_modules /Users/srikanthparimi/OfficeApp/dealgate-s21-crm-facet-wiring/web/node_modules`. No package changes or shared node runtime writes. Frontend tests are request-coordination/unit coverage, not an integrated application journey. Runtime was serialized under the lead's explicitly released slot and released after both processes exited.

## Integration Dependencies

- Lead subsequently extended ownership to only the `DealDetail.tsx:152` facet call. It now explicitly requests `{ include_closed: true }`, preserving the previous all-deal owner population for next-action owner options. This one-line follow-up was made after slot release; lead owns full-web integration regression.
- Lead owns integrated TypeScript checking, broader regression and browser/staging proof.
- Existing facet DTO still cannot distinguish unavailable metadata from an empty matching population; no richer availability contract was invented in this increment.
