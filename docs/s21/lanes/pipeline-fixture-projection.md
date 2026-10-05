# Pipeline Fixture Projection

Branch `s21/pipeline-fixture-projection`, baseline
`a5ee0e8cc3f79d9ed25414708c55036e0c068622`. Implements the accepted T17/CO-05
read-projection contract only. No fixture/release authorization changes,
migrations, connector changes, provider calls, staging or full-journey claims.

## Changes

The existing trusted fixture scoper populates a default-empty internal exact-ID
capability after participant, issuer, owner, tenant/environment and expiry
validation. Shared Pipeline predicates admit only `sow_upload` rows carrying
that capability, alongside existing authorized CRM rows. Duplicated CRM-only
predicates no longer remove those authorized fixtures from legacy reads,
detail, facets or client totals. Connector source enumeration and linkage
remain unchanged and CRM-only. Normal users still exclude fixture clients.

Pipeline rows/detail/legacy rows expose `source_origin`, with
`local_test_fixture` only for projected local sources. The UI displays a small
Local test fixture marker and no longer claims every listed source is HubSpot.
Stored source/external IDs remain unchanged; no CRM fields are invented.

Lead expanded ownership narrowly to `reports.py`'s Pipeline CSV function.
Export now applies the same trusted scope, fetches all pages instead of stopping
at 1000 rows, and includes additive `source_origin`. Other report endpoints are
unchanged. Exact 1002-row export membership is checked, not just a paginator.

An added real HTTP search assertion exposed existing route shadowing: the
preceding unconstrained `/deals/{opportunity_id}` route consumed `search` and
returned 422. A UUID path converter preserves valid detail URLs and lets the
static search route run. This was independently reproduced before the fix.

## Verification

Tests were authored before production edits while the lead owned runtime.
After the slot grant, the three owned backend files were temporarily restored
to baseline via apply_patch, with the fix preserved, then restored again.
Initial run exposed a test-only tuple/list empty-container mismatch; corrected
to exact ID membership without changing expected authorization outcomes.
The definitive baseline run was **4 failed, 10 passed in 6.07s**: owner and
participant row absence, HTTP 404 detail, and 1000-row export truncation.

Fixed focused run: **14 passed in 7.36s**. Affected regression run:
**75 passed in 38.98s**, with two existing FastAPI lifespan deprecation warnings.
The separate HTTP search assertion then failed 422 in 3.08s; after the route fix
the unchanged focused suite passed **14/14 in 8.72s**.

Commands (own `api` cwd; readonly interpreter, own SQLite; no shared database):

```sh
env -u DEALGATE_POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest \
  tests/test_s21_pipeline_fixture_projection.py \
  tests/test_s21_pipeline_population.py \
  tests/test_hubspot_pipeline_query_service.py \
  tests/test_s21_pipeline_independent.py \
  tests/test_s21_project_source_scope.py -q -p no:cacheprovider -o addopts= --tb=short
```

Focused executions use the same command with only the new file or named HTTP
test. Existing tests and project-source rejection assertions are unchanged.
Cases include authorized issuer/participant, unauthorized test and normal
users, expiry, wrong tenant/environment, revoked issuer, mismatched owner,
external-ID contamination, archive, forged label, same-client unissued sibling,
internal-capability URL injection, absent CRM fields, scoped facets/search,
CSV membership/provenance and full pagination. Browser marker proof and the
combined connected local/staging journey remain lead-owned.

Private APFS node_modules clone was made after checking 18 GiB free. No shared
generated writes or installation. Sequential `npm exec -- tsc --noEmit` passed
with exit 0. Runtime released; no processes remain.

## Independent QA Follow-up

QA report `561b46d` correctly identified two remaining export defects: mutable
OFFSET pages under READ COMMITTED and ignored business query filters. This
follow-up owns only the export function/imports, its focused tests, this report
and the explicitly authorized new private PostgreSQL proof script.

Export now establishes PostgreSQL REPEATABLE READ and READ ONLY before any
group/watchlist, grant authorization, totals or row query. An already-active
PostgreSQL transaction returns 409 rather than quietly accepting a weaker
snapshot. Rows are fully materialized before streaming and share one reference
time. Request session dependencies currently perform no preceding DB query;
the explicit active-transaction guard also catches future dependency changes.
Fresh local SQLite sessions explicitly BEGIN; SQLite results are not claimed
as PostgreSQL MVCC proof.

The export accepts the same typed business filter values and uses Pipeline's
existing `_parse_filters`, `_resolve_scope`, `_parse_sort` and trusted fixture
scoper. Unknown query parameters return 400 instead of silently broadening an
export. Export intentionally has no page/page_size parameters: it exports all
matches. The total row now says matching (rather than incorrectly saying open
when an explicit closed-state filter is used). Other report endpoints remain
unchanged.

Observed original-export red: **6 failed, 15 passed in 12.10s** (ignored pipeline,
search, stage, owner, client filters and unknown query). Fixed run:
**21 passed in 11.62s**. A subsequent owner+stage+search intersection also asserts
one exact source and USD 120 against list/summary/CSV, excluding two deliberately
near-matching sources. Final affected suite: **83 passed in 59.54s**, two existing
FastAPI deprecation warnings. Runtime released; no processes remain.

### Actual PostgreSQL Proof

`scripts/s21_pipeline_export_pg.py` requires the explicit local admin DSN,
literal user/host/port/database and no query overrides. It clears libpq override
variables; creates a UUID-named private database with unique ownership comment;
migrates that database through the actual Alembic head; and only drops the exact
same name/OID/owner/comment, never FORCE. It does not reset `s21_journey`,
`s21_schema` or `s21_lead`. Container identity was checked as
`dealgate-s21-lead-db`, `pgvector/pgvector:pg16`, bound 127.0.0.1:55421.

The proof helper in the new test file is explicitly invoked by that standalone
script, not silently skipped by the default SQLite suite. Its interleaving hook
calls the real query service and commits through a distinct PostgreSQL session;
it does not replace feature responses. Seed 1002 uniquely named rows with ordered
close dates, row 1001 worth USD 1001 and all others USD 1 (independent total USD 2002).
After page 1, writer moves the first row to the end and changes its price/name
and the company name. Assertions check every original name, every exact amount,
original company values, totals, and configured isolation before authorization.
Also verify the writer actually committed and active-transaction refusal 409.

Original export failed the exact original-population assertion in real
PostgreSQL (session 77501); scratch
`s21_pipeline_export_b7c69dade67c40eebb863f86a8951bf6` cleanup confirmed.
Fixed export passed (session 73813; process 32717; PostgreSQL reader 5838 and
writer 5839). Scratch
`s21_pipeline_export_dafd333dfdf64e11a899ff27500bfdde` cleanup confirmed.
Migration head in both runs: `20261002_0061_automation_jobs`.
The proof's reported source revision was parent `2d545384` plus this uncommitted
follow-up working diff; final commit identifies those tested changes.

```sh
env PYTHONDONTWRITEBYTECODE=1 \
  S21_PIPELINE_EXPORT_ADMIN_URL=postgresql+psycopg://s21@127.0.0.1:55421/postgres \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -B \
  scripts/s21_pipeline_export_pg.py
```

No production/staging database, external provider or deployment was used.
