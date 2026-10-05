# Pipeline Fixture Boundary

Author-only assessment on `s21/connected-actuals-automation`, following
`d322e0b`. No application/script changes, runtime, tests, database or provider
operations. The lead owns the integrated running journey. This document is a
proposed contract adjustment, not implemented or verified behavior.

## Contract And Existing Path

The v3 directive's T17 requires Pipeline -> client -> named deal with no SOW ->
upload -> workspace -> signature -> handoff, plus navigation/count/gate and
leak checks. CO-05 expressly permits an authorized existing mirrored deal OR
an isolated run-tagged fixture through supported application paths, without
HubSpot writes. It additionally requires actuals, negative signature guards,
idempotent project creation, combined staging evidence and owned cleanup.
Sources: `docs/directives/s21-forecast-implementation.md`, T17 and CO-05;
`docs/s21/acceptance.md`, T17/T21/T30. A local entry-path improvement alone
cannot close these scenarios or CO-05.

Existing supported API sequence:

1. `POST /dev/test-fixtures` under a persisted authorized test administrator
   creates a NEW client and `source="sow_upload"` opportunity plus an audited,
   expiring, tenant/environment-scoped grant. Input only accepts label, known
   test reviewer IDs and validity hours; no existing account adoption.
2. `GET /deals` and `GET /deals/{id}` expose the authorized fixture. Existing
   upload, commercial, approval, signature and release APIs can then retain
   its exact source lineage without inventing a CRM identity.
3. Pipeline list/detail currently cannot expose that fixture. Its shared base
   predicate ANDs `source == "hubspot"` with trusted authorization filters.
   Additional hardcoded source predicates exist in older query entry points.
   Thus `/pipeline/opportunities/{id}` returns404 even for the grant owner.

There is no existing supported API flag that safely closes this gap. Calling
the Deal page directly, injecting a route response, setting a fake external
ID, or changing source to `hubspot` does not prove the Pipeline beginning.

## Existing Authority Must Stay Intact

`api/app/services/test_fixtures.py:account_scope` validates the issuance audit,
runtime tenant/environment, expiry, persisted issuer role, participant IDs,
client/owner relationship and exact opportunity identity. External company or
deal IDs invalidate fixture authority. `user_allowed` separates test identities
from business records rather than granting administrators a blanket bypass.

`api/app/services/hubspot_pipeline.py:scope_pipeline_filters` already computes
authorized client/deal IDs before aggregation/pagination. Normal users get
fixture clients hidden; test users get only valid granted opportunities.
This is the correct authority to reuse, not names, URL parameters, run tags,
local admin status alone or a caller-supplied list of IDs.

`api/app/services/project_source.py:capture_project_scope` additionally rejects
a fixture with `source="hubspot"` or external IDs. It captures the grant ID
and original SOW/GM/account/owner identity. Do not weaken that condition, change
approval isolation, or relabel the fixture as CRM to satisfy a read query.

## Smallest Recommended Adjustment

Keep fixture creation, stored source, external IDs, grants and release capture
unchanged. Extend ONLY the authorized Pipeline read population with an explicit
internal `authorized_fixture_opportunity_ids` tuple, default empty, populated
by `scope_pipeline_filters` after its existing per-account/per-deal validation.
Only validated test participants receive IDs. It is not an HTTP request field,
saved-view setting or user-editable capability.

One shared source predicate becomes conceptually:

```text
source == hubspot
OR (source == sow_upload AND opportunity.id IN server_validated_fixture_ids)
```

Existing authorization, hidden-client, archive and all business filters still
apply to the complete result. An empty tuple grants nothing. Normal users,
unscoped service callers and test users without a valid grant retain their old
population. Do not simply remove the HubSpot predicate or include every local
SOW-upload deal. The optional population is valid only in the grant's issued
environment; a local grant must never qualify in staging.

Use the same predicate for list, summary, clients/counts, facets, search,
export and deep-link detail. The current `_base_query` duplicates the HubSpot
check before `_base_opportunity_filter`; both must converge on one predicate.
`get_opportunity_row` also hardcodes HubSpot source and needs the same scoped
filter passed through its router caller (default remains strictly CRM-only).
Audit every other hardcoded predicate for whether it is a Pipeline view or a
connector operation. Keep `is_hubspot_linked`, sync/backfill/metadata queries
and connector source enumerators genuinely HubSpot-only. Do not turn fixture
presence into CRM linkage or send connector writebacks.

Preserve truthful names and provenance: local fixture gets its actual named
client/deal, null external identifiers and no invented CRM owner/pipeline/stage
or BU metadata. Add an additive response provenance field such as
`source_origin: "hubspot" | "local_test_fixture"`, server-derived, if the UI
otherwise implies every row is HubSpot sourced. Render a restrained local-test
source marker for fixture participants using existing test-mode conventions.
CRM filters should still honestly exclude the fixture when metadata is absent;
do not create fake pipeline/stage IDs to make filters match. Scope/counts with
no such filter should include its one exact deal. The fixture must never appear
in normal users' Pipeline or aggregate counts.

This is an authorized local fixture projection onto existing Pipeline reads,
NOT a fabricated HubSpot mirror record. If a later test needs a local mirrored
source snapshot with meaningful stage labels, design a separate explicitly
synthetic snapshot contract, preserving null real external IDs and fixture
origin. That is larger than the entry-path fix and must not be quietly adopted
as live HubSpot data. No such snapshot is needed for the no-SOW entry journey.

## Ownership And Test Order

Lead assigns the CRM lane `api/app/services/hubspot_pipeline.py` and
`api/app/routers/pipeline.py` for the read-population adjustment and additive
DTO. Any provenance rendering/types should have an explicitly assigned frontend
owner. No fixture issuance, project-source, approval, migration or infrastructure
change is required for the recommended adjustment. Shared contract/route
ownership and integration remain with the lead.

Tests first in the existing Pipeline population/query tests or one new focused
file, with independent QA preserving current tests:

- Valid fresh fixture: owner and explicitly granted participant see exactly
  that deal through list/detail/search/client counts/summary/export before any
  SOW. Unauthorized test identity sees none; ordinary user sees none, including
  direct IDs and all aggregates. CRM rows preserve existing behavior.
- Expired, foreign tenant/environment, revoked issuer, archived client/deal,
  forged label, extra opportunity under the same client, mismatched owner and
  external-ID contamination all fail closed. Empty grant list stays empty.
- Query-string or saved-view attempts to supply fixture IDs cannot enable
  scope. Pagination, filtering and counts use the same pre-scoped population.
  No CRM source fields are inferred or written; connector linkage stays false.
- Full real release on the same now-visible fixture retains valid
  `fixture_grant_id`, unchanged source classification and original identities.
  Keep `test_s21_project_source_scope.py` assertions unchanged; add a connected
  regression proving the new read path does not relax release authorization.
- Browser test enters Pipeline, client then the named no-SOW Deal, verifies
  honest absent CRM metadata/local marker and no premature approval workspace,
  uploads using the actual API, and continues the existing same-source journey.
  Include Back/reload/header and one-project assertions required by T17/CO-05.
- Run the existing leak gate and route inventory, then combined staging proof
  with supported environment-specific issuance and exact owned-data cleanup.

Candidate existing test locations: `api/tests/test_s21_pipeline_population.py`,
`api/tests/test_hubspot_pipeline_query_service.py`,
`api/tests/test_s21_pipeline_independent.py`,
`api/tests/test_s21_project_source_scope.py`, and the retained-provenance legacy
`tests/e2e/specs/s20/t44-full-journey.spec.ts` required by CO-05. Lead/QA choose
new exact node IDs; this report claims no collection or execution.

## Proof Boundary

After implementation, a local fixture can prove actual routing, named identity,
read/write service integration, grants, reviews, release and financial lineage
without HubSpot writes. It cannot prove source-adapter parity, live CRM identity,
webhook latency, consumer deployment, Cognito or email delivery. Those remain
the separately identified provider contracts and human canary (T36/T42 etc.).
Using an existing real mirrored deal instead is explicitly allowed by v3 but
requires appropriately authorized real identities and approved business-safe
test scope; test reviewers cannot be attached to it to bypass fixture rules.
The current script's Pipeline-blocked disclosure stays correct until a tested
read-contract adjustment is actually integrated and executed.
