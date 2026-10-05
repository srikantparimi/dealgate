# Independent Pipeline And Signatory Review

Review date: 2026-10-02. Budget: approximately 10 minutes, static inspection only.
Reviewed integration commits `9f6af54780d602680617498735be32dcef5e4ca9`
(typed signatories) and `a6c9e7c4df132f2e119b0c47c0d46aebb2910768`
(authorized fixture projection/export) using `git show`. Line references below
are against those snapshots, not the older application files in this QA tree.
Only this report was written. No tests, collection, application imports,
providers, database, browser, installation or deployment were run. These are
static findings and proposed reproductions, not executed proof or requirement
closure. Existing focused/browser evidence is not independently reproduced here.

## Findings

### 1. P2: Multi-page export can silently duplicate and omit opportunities

New behavior in `api/app/routers/reports.py:718-725` concatenates independently
queried pages and stops using their current total. The underlying query applies
OFFSET at `api/app/services/hubspot_pipeline.py:1360-1363`; the default order
contains mutable attention, action date and close date (`:647-651`). The UUID
tiebreak (`:1674-1676`) stabilizes ties, not changes between statements. The
session configuration (`api/app/db/session.py:22-33`) does not request a stable
export snapshot. Under PostgreSQL READ COMMITTED, each statement can see a
different committed population even within one session transaction.

Concrete two-session schedule: seed 1002 authorized open business deals with
equal attention/action state and strictly increasing close dates. Export reads
summary and page 1 (deals 1 through 1000). In a second session move deal 1's close
date after deal 1002 and commit before export's second page SELECT. OFFSET 1000
now returns deals 1002 and 1. The CSV contains deal 1 twice, omits deal 1001, and
still reports 1002 rows, so a count-only assertion passes. If deal 1001 is USD
1001 and every other deal USD 1, the summary is USD 2002 but exported rows sum to
USD 1002. No unauthorized actor or invalid fixture is needed.

Suggested regression: actual separate PostgreSQL sessions with an explicit
barrier after the first page read; assert unique IDs/exact initial population
and totals, not merely row count. The committed 1002-row test
(`api/tests/test_s21_pipeline_fixture_projection.py:152-170`) has no concurrent
writer and cannot establish this property. Use one consistent population for
summary and rows; keyset pagination alone does not freeze mutable sort keys or
financial values.

### 2. P2: CSV ignores requested business filters

Inherited behavior remains in the touched export path, not a newly introduced
authorization bypass. `api/app/routers/reports.py:702-705` accepts no filter
parameters and `:717` always constructs only `open_closed="open"`. This differs
from the supported-projection contract's shared filtered export population and
the endpoint's own "current open-pipeline filter set" description.

Concrete reproduction: a valid participant's issued local deal has no CRM
pipeline. GET `/pipeline/opportunities?pipeline=fake-pipeline` returns zero;
GET `/reports/pipeline/export.csv?pipeline=fake-pipeline` silently ignores the
same filter and exports the local deal with total 1. Likewise owner/client,
readiness and other filters are not parsed. This is over-export within the
already-authorized population, not cross-participant disclosure. The committed
HTTP test checks the filtered list at `test_s21_pipeline_fixture_projection.py:136`
but then exports without filters at `:137`.

Suggested regression: matching HTTP list/summary/CSV requests with a zero-match
filter, followed by a nontrivial intersection, compare exact IDs and totals.
If this endpoint is intentionally a global-open report instead, that is an
explicit contract decision; it must not stand as proof of filtered export parity.

### 3. P2: Current typed signatory wrapper is not locally schema-validated

The new person-object checks correctly reject non-list/non-object values,
empty names and invalid role types (`api/app/integrations/bedrock_sow_extract.py:532-541`).
However, `signatories={"page_ref": 1}` bypasses those checks because `.get("value")`
returns None. The inherited `_validate_field` then synthesizes
`{"value": null, "page_ref": 1, "status": "unconfirmed"}` (`:184-204`) instead of
returning ManualRequired. A valid nonempty value with omitted status is also
silently accepted. Both violate the current required wrapper keys in `:309`;
they are not historical stored identities, which the change explicitly intends
to preserve separately. Extra wrapper keys are similarly discarded. A wrapper
with `status=[]` reaches set membership at `:192` and raises TypeError outside
the decoder's ValueError-only handler (`:549`).

Suggested provider-boundary regression: start with the complete valid forced-tool
response and replace only the dedicated signatories entry with each malformed
wrapper above. Assert ManualRequired and one provider call, not a fabricated
unconfirmed wrapper or uncaught exception. Do not tighten historical persisted
string readers to solve this current-provider boundary gap. Existing added
tests vary the person value, not the enclosing wrapper. This review does not
claim a signature/approval bypass; downstream human confirmation remains a
separate gate. The shared wrapper weakness predates these commits but remains
reachable through the new decoder path.

## Boundaries That Held In Static Inspection

- Fixture capability defaults empty and is derived by `scope_pipeline_filters`
  from the existing account/issuer/participant/owner/tenant/environment/expiry
  checks, not request parameters. The exact opportunity-ID intersection excludes
  an unissued sibling. Normal readers hide granted client IDs; unscoped local
  rows do not enter the new source predicate. No concrete new grant bypass was
  identified in the bounded paths inspected.
- Detail now passes scoped filters to both reads; list, clients, summary and
  facets share the source predicate. Connector enumerators stay HubSpot-only;
  the change does not write external IDs or relax issuance/release guards.
  The DTO/row marker distinguishes a local test fixture from CRM data.
- Dedicated name/role wire objects and strict nonempty person checks avoid the
  observed name/organization concatenation without weakening downstream name
  comparison. `signed_sow.py:186-224` already handles typed names and legacy
  strings; role differences remain explicitly outside that name comparison.
- Provider semantic fidelity, contradictory identities, full real release on
  the projected fixture, live HubSpot and staging behavior were not verified.
  This report supplies no independent pass counts and closes no requirement.
