# S21 Integration Contracts

Authority: [complete v3 directive](../directives/s21-forecast-implementation.md). No scope reduction. All financial math remains in `api/app/gm`; extend existing engine/core/policy rather than creating a Forecast margin engine.

## Explicit Reconciliations

1. S17 and v3 override the old blueprint's agreement signature gate. NDA/MSA are client documents; presence never implies legal clearance or blocks governance.
2. v3 reverses Archive and narrows old deletion behavior: retain projects with activity/timesheets/invoices/actuals, detach source. Delete only proven empty generated project shells. Preserve parent deal/client and independent opportunities. A minimal tombstone fences stale events; never retain deleted document payloads in it.
3. Preserve mandatory HR review. Add mandatory Sales; dated, timezone-aware Delivery OOO alone permits the specified fallback. No test-user substitute for missing real eligibility or mail readiness.
4. Historical S20 states are source claims. S21F:T01-T45 differ from S20:T01-T44, especially T32/T34/FINAL-T38 and the legacy skipped t44 journey.
5. Unknown is not zero. Missing owner/year/currency/cost/probability/calendar/FX is an explicit unresolved input. Manual uploader identity never stands in for CRM ownership.
6. Financial approval binds immutable source, commercial calculation and policy versions. Pending amendments leave signed schedules active. Activation is effective-date/version checked and idempotent.
7. Terraform-only infrastructure, one lead, state locking, repository wrapper, whole-root plan and human confirmation remain mandatory. No scripted yes, auto-approve, targeted apply hiding drift or saved-plan bypass. Old D5 CLI task-registration steps are not authorization to bypass these controls.
8. Repository time limits cause a checkpoint, not an incomplete deployment. No main merge or production deployment until explicit product-owner staging approval. A subsequent main-image verification remains required.

## Existing Boundaries

CRM reads use `services/hubspot_pipeline.py` and its filters, not a second query model. HubSpot owns source identity/stage/CRM ownership; local owners and actions remain separate. External IDs are strings. Stage keys include pipeline; multi-company associations use one explicit reporting account.

Governance uses existing `approval_routing`, `approval_workflow`, `signed_sow`, `handoff`, `delivery_acceptance`, `project_lifecycle` and `deletion` services. Models remain in `api/app/models`; lead owns schema and migration order. Roles and transitions are checked server-side and audited in the same transaction. Lead reviews every extension of shared lifecycle behavior.

Forecast extends existing `models/forecast.py`, `models/actual.py`, `services/forecast.py` and related routers. New planning concepts may have dedicated models, but never duplicate signed contract truth. Existing Finance/People sources are inventoried first; absent connectors require validated permissioned managed imports, not fake live status.

### Forecast Planning Increment (0050)

Existing weekly `forecast_period` remains compatible. Add forecast plan identity,
immutable plan versions, immutable calculated schedules, a version-keyed job
outbox and explicit conversion links. Plans reference account and optional CRM
deal; they cannot write to HubSpot or manufacture a signed status. Lifecycle,
probability/provenance, assumptions, source commercial inputs and economic scope
are versioned together. Write requests carry an expected version and creation
idempotency key. All mutations audit and enqueue atomically. One source version
per calculated snapshot; old/out-of-order jobs are obsolete, not fresh totals.

Pure `app.gm.forecast` performs scenario/FX/coverage arithmetic. Signed rows come
from actual signed/released approval-bound GM snapshots. Conversion links retire
only the explicit scope fraction in covered months; drafts never create signed
coverage. Legacy sources without confirmed monthly allocation remain visible as
unresolved, not silently spread by month. Account rows and scoped company totals
reuse one authorized population before paging/export. A signed row with unknown
cost can expose known revenue but never complete GM; unsigned incomplete costs
remain excluded. Unavoidable cost is an identified subset, not an extra charge.

Reporting timezone/currency must be explicitly configured; absent configuration
is an actionable error, never guessed from the uploader. Finance/Delivery/CEO/
SystemAdmin have organizational planning reads; Sales is limited to owned plans
and deals and receives My portfolio labels plus cost redaction. HR demand views
will be separate from financial permission. API/UI/import, People demand,
automation and deployed acceptance remain required, not closed by this contract.

## Commercial Contract

Versioned pricing components contain ID, model/profile version, currency, source evidence, service term, independent billing cadence, effective period, revenue inputs, resource/calendar references and explicit cost basis. Delivery workstream is distinct from pricing. Supported profiles: fixed assignment, recurring MSP, calendar staff augmentation, T&M, milestones, unit/story point and hybrid. Unsupported models preserve drafts and report validation; AI cannot author executable formulas.

Canonical schedule result: source/version/calculation/policy/calendar IDs; timezone; component and location; month; scheduled/billable/paid hours; Decimal revenue/cost; completeness/reasons; immutable assumptions. Date overlap is inclusive; allocation/headcount apply once. Fixed total allocations conserve minor units; allocation basis must be confirmed. Paid holidays can add cost without billed revenue. US 35% and India/offshore 50% floors are unrounded component/location tests; aggregate GM is revenue weighted. Zero or incomplete revenue is not assessed; incomplete cost never passes Finance.

Initial engine interface lives under `app.gm`: frozen typed calendar/assignment inputs and monthly result, followed by typed component schedules. Existing `compute_gm` remains margin authority; agreed adapter uses scheduled quantities without applying allocation twice. Lead integrates persistence and callers after review.

### Persisted Commercial GM Contract (0049)

The existing immutable `gm_model` owns `commercial_inputs` and
`commercial_snapshot`; no second signed-contract store. Canonical JSON uses
Decimal strings and typed dataclass schemas, rejects floats/discarded fields,
and binds every hybrid child to the exact SOW ID/version and policy version.
The snapshot freezes schedule, outcome, calculation identity, policy floors
and written confirmation/change reason. Reads restore that snapshot, never
silently recalculate signed economics under later engine code. Revenue cache
columns allow NULL for unassessed models and unscaled NUMERIC for precision;
the reversible migration refuses a lossy downgrade with commercial history.

`GET /delivery-model/commercial/profiles` returns registry and active policy.
`POST /delivery-model/commercial/preview` accepts a canonical component.
`POST /delivery-model/{deal}/commercial/versions` accepts `sow_version_id`,
`expected_gm_model_id` (nullable only when no prior SOW model), `inputs` and
`change_reason`. Delivery/SystemAdmin writes; stale writes return 409. Existing
GM reads/approval hashing use the same persisted version. Raw inputs/snapshots
are removed for readers without cost entitlement. A draft does not void a
verified signed/released contract; amendment activation remains a separate,
unfinished lifecycle requirement. Event publication and all-profile browser
editing are still pending and not implied by this storage increment.

## Forecast / Actual / People Contract

07:52 UTC Next opportunities increment: expose persisted plan rows under the
existing scoped Forecast filter shell, with explicit Local forecast only or
linked authoritative deal identity, assumptions/evidence and worker state.
Assumption edits use a dedicated optimistic-concurrency endpoint preserving
all commercial inputs, scope, FX, scenario and selected state server-side;
caller supplies expected version, probability/source, assumptions, lifecycle
and written reason only. Same existing planning-write authorization and tenant/
account boundaries apply. No implicit CRM writes, signature, quote or hire.
Read-only users get no editable controls. No fake growth suggestions: source
continuity/generation/CRM-promotion workflows remain separate visible gaps.

### Financial Actuals Increment (0051)

No Finance connector exists in the inspected application; the existing CSV
actuals service is resource/month upsert only and has no recognized/billed/cash
source basis. Extend that service/router/model ownership with a versioned managed
financial import, preserving the legacy endpoint without relabeling its data.

`POST /actuals/financial-import` (Finance/SystemAdmin) accepts source_system,
idempotency_key and rows with canonical account, optional exact GM source,
source_id, revision/expected_previous_revision, period_month, measure
(recognized_revenue/billed/cash_collected/delivery_cost), Decimal amount string,
currency, source_date and written reason. Optional FX rate/version/date must
be explicit. New immutable revisions replace the same source row; distinct
measures stay distinct. Idempotent replay returns one batch; changed replay or
stale correction conflicts. Validate the entire batch before any financial row
is written; failures retain an error report and audit. Tenant/environment and
trusted fixture scope are enforced before every write/read.

0051 owns financial_import_batch and financial_actual tables in models/actual.py.
Source identity/revision is unique per tenant/environment/system. Account/GM
foreign keys detach on deletion, while original IDs and financial facts remain
for Finance history; no source document text is retained. Downgrade refuses to
discard ledger history. Existing actual_period semantics remain unchanged.

`GET /actuals/financial-imports` and `/actuals/financial-records` expose permitted
history/current revisions. Forecast may display separate recognized/billed/cash
and cost totals with source IDs and currency/FX provenance; it must not add them
to a whole-month service schedule or imply partial-month blending without an
explicit matching service-coverage contract. This increment does not invent
such coverage from an invoice date. No live Finance connection is claimed.

Forecast rows reference tenant/environment/account/deal/SOW version, economic scope, effective period, scenario, source status, explicit probability, currency/FX revision and as-of watermark. Committed = active signed. Expected weights eligible unsigned revenue AND avoidable cost once; Upside includes eligible full value. Incomplete inputs are excluded with reasons, not silently zero. Partial conversion subtracts covered economic scope; alternatives are mutually exclusive.

Default report: organization-local current quarter, then next two FULL quarters, with 1/2/4-quarter choices. Current quarter never leaks into future-only total. Account totals reconcile to authorized company totals before display rounding. Limited readers see portfolio/selected scope labels, never unauthorized company totals.

Actual imports identify source row/version, basis (billed/recognized/collected), service period, currency, scope and corrections. Actuals replace matching covered forecast only on the SAME basis; no actuals source means signed schedule with actuals unavailable. Preserve history through SOW deletion.

Demand keeps full headcount and dated FTE regardless of win probability. Availability is freshness-marked and allocation-constrained globally, matched once across overlapping demand. People planning creates versioned sourcing drafts, never hires/reservations. HR views omit financial fields without entitlement.

07:58 UTC People matching increment: accept the proposed exact-match fallback
from lanes/people-demand-contract.md. Pure interval matching uses explicit
skills, level, role, location and timezone; no inferred equivalence. Gross
capacity and dated commitments are distinct and subtracted once. Draft proposal
ordering is committed demand then start date then stable identity; report its
version as a proposal, not approved company staffing policy. Full integer slots
are not probability weighted; two half-time roles can share capacity, but two
slots within one quantity require two distinct people. Explicit retained-person
links carry continuity, not automatic new hires. No reservation is created.
Managed imports remain fallback pending any real connector; no directory is
invented from application users. Missing skills/rules/continuity remain unresolved.

## API / Event Rules

Use existing API patterns; request models validate identity, permission and optimistic version before writes. New responses carry schema/calculation version, as_of, scope, completeness and missing-input reasons. Lists and exports share authorized filters BEFORE pagination; stable sort and snapshot totals. No frontend-only truth or browser-storage-only workflow.

Domain mutations write audit + transactional outbox atomically. Events carry tenant/environment, aggregate ID, source version, schema version, event ID, occurred_at and correlation/run ownership. Consumers reject stale versions, dedupe business effects, honor deletion fences, bound retries and surface dead-letter/error state. Version-checked snapshots cannot mix old and new component results. Names/tags alone never confer trusted test provenance.

## Schema Order / Release Gates

### Deletion / Retention Increment (0052 Reserved)

CO-09 cleanup selection uses only server-issued `test.fixture_created` audit
grants, never a name or NULL HubSpot ID. Require exactly one grant, matching
runtime tenant/environment, current test-admin issuer, the granted deal owned
by that issuer, no mirrored account/deal, no additional ungranted deals, and
expired validity plus minimum age. Missing or malformed provenance fails closed.
Default age is 24 hours; malformed, negative and nonfinite values are errors.
Zero age additionally requires explicit exact run and owner arguments; it does
not bypass active-run protection. Default execution produces a dry-run manifest.
Apply rechecks provenance under account/deal locks and uses the same retained
financial-fact deletion path as intentional client deletion, not the legacy
best-effort cascade. Until that path is proved, scheduled activation remains off.

S21-01/CO-09 override the old Archive-only behavior, not authorization or audit
immutability. Extend the existing deletion service and routes. An authorized
SOW request locks its exact SOW and owned versions, records an idempotent minimal
tombstone/fence and durable cleanup job in the same transaction as database
removal and audit. Never scope packages by parent opportunity alone: sibling
SOW packages, comments, agreements and independent forecasts must survive.
The result returns job/status/counts and retained dependencies. Pending object
cleanup is not reported as complete; failed work remains retryable and visible.

Keep every existing project unless independently proved an empty generated shell;
the initial safe implementation retains all projects and detaches source FKs.
Retain frozen project baseline and actual financial facts, original source IDs,
and explicit source-deleted marker. Preserve legacy actual periods as well as
0051 financial facts. Read models must use retained metadata when links are NULL,
not hide the project through inner joins. This is financial retention, not a
copy of the deleted upload or extracted document in the tombstone.

Persist exact owned storage bucket/key references only in the cleanup job until
all versions and delete markers are removed; clear them after success. Do not
delete an object referenced by a surviving SOW. Cancel owned notifications,
review actions, renewals, signature work and upload jobs, and fence late workers
by their stable version/package/source IDs. Existing independent deal writeback
must recompute the surviving deal state, not reapply stale removed-SOW status.
No provider cancellation is claimed where only manual signed upload exists.

0052 is lead-owned, additive job/fence tables plus nullable retained source links
and original identities. Tests begin with sibling-SOW preservation, actual/project
retention, repeat requests and object failure/late-worker fences. Real migrated
PostgreSQL and versioned S3 proof are required before activation; SQLite alone
cannot establish cascades, transactional fencing or storage cleanup.

0053 is reserved for generic parent deletion jobs: explicit subject type/ID,
nullable SOW identity, unique tenant/environment/subject identity. Backfill0052
jobs as SOW subjects without changing their IDs or status. Parent jobs depend
on child jobs and cannot report complete before their owned storage and child
cleanup completes. Client/opportunity APIs use the same retained SOW path;
mirrored parent deletion is refused before any mutation. Retained project and
actual source identities survive detached parent links. Parent agreements get
exact-key durable cleanup, never swallowed best-effort errors. Repeated requests
return the scoped original job. Downgrade refuses to discard parent-job history.
The proposed CRM metadata revision moves to0054; no other writer owns migrations.

06:45 UTC CRM expansion decision: adopt the source-observation and availability
contract in lanes/crm-source-review.md (e555140), split into ordered small steps.
0054 adds nullable external owner/observation and BU value/mapping-version/
observation fields on Client and Opportunity; Client source modified/seen times;
explicit local assignee distinct from CRM owner; nullable mapping identity plus
unknown/configured/absent/ambiguous/unavailable state, reason, checked/success
timestamps, positive mapping version, evidence and selecting actor. Existing
rows remain unobserved/unknown; no inferred source backfill or provider calls.
Downgrade refuses loss of observations/configuration or invalid old shapes.
Existing metadata compatibility is preserved until the next tested adapter
increment; new fields alone do not claim corrected source facts.

0055 is reserved for atomic scan lease/cursor/generation and pipeline-scoped
stage identity after compatibility tests.0056 is the next People schema slot,
following review of lanes/people-demand-contract.md. No worker may occupy these
revisions or assume those contracts are already implemented. All migrations
and deployed activation remain lead-owned; current deployed schema unchanged.

07:23 UTC refinement:0055 is the backward-compatible scan-state expansion:
BIGINT scan_generation, idle/scanning/finalizing/completed/failed phase,
nonnegative failure count, nullable immutable JSON context, UUID lease token
and expiry, nullable Opportunity seen-generation; unique stage(pipeline_id,id)
added while retaining legacy global PK(id). Existing rows remain idle with
no invented lease/context/seen evidence. Downgrade refuses any populated new
evidence or out-of-range generation. Qualified-reader activation and removal
of global stage uniqueness require a later explicit contract migration after
all deployed writers are compatible;0055 alone does not enable colliding IDs.
This preserves0056People sequencing without conflating expansion and cutover.

Lead reserves next revisions after checking the actual single head. Order: tenant/test provenance and deletion fence; immutable calendars/components and routing windows; plans/actual import/People demand; snapshots/rules/outbox additions. Exact DDL follows existing-schema review. Additive expand/backfill/validate before activation; resumable batches, no business-data purge rollback. No lane writes migrations.

Every gate requires attributable run evidence. Code, local pass, integrated pass, deployment and human acceptance are separate fields. Financial expected values come from QA's independent oracles. No test retries, weaker assertions or mock feature API responses to close a gate.

08:32 UTC People expansion refinement:0056 is the managed workforce supply
snapshot family only. A scoped PeopleSource row serializes full-source imports;
immutable PeopleImportBatch revisions have request hash/key, source-as-of,
actor/reason and predecessor. WorkforcePerson stores stable source/person keys;
immutable WorkforceVersion stores display/capability evidence per batch;
WorkforceInterval stores inclusive gross-capacity or committed/reserved/hired
assignment dates and exact NUMERIC allocation, with authoritative source key.
No costs, salaries or rates are accepted. Current supply reads ONLY the latest
accepted source snapshot, not a mixture of independently latest people. An
omitted person is absent from current supply but historical versions survive.
An empty source snapshot is explicit and auditable, never inferred from a failed
connector call. Imports require expected previous batch, monotonic source-as-of,
explicit timezone, gross-capacity basis and written reason; conflicting replay
is 409. Whole invalid payloads reject atomically, never partially import.
No users become staff automatically and no HR connector is claimed.

0057 is reserved for demand publication/source continuity;0058 for sourcing
revision/event/snapshot/rule persistence after0056 tests. Both remain lead-owned.
This split changes no acceptance scope. Existing pure allocation commitment
source_id must match stable demand-line identity for continuity credit; mere
person-name coincidence cannot reclaim another project's commitment. Proposal
matching is not reservation or hiring authorization.

Managed workforce sources additionally carry server-derived `test_fixture`
provenance in their identity and reads. Test identities cannot import into or
read real supply, and real HR cannot accidentally match test roster people.
The request cannot choose this flag. Preserve this split in global allocation.

09:00 UTC0057 publication detail: one stable DemandPublication per source plan
or retained delivery project, scoped by tenant/environment/test provenance.
Exactly one plan_id/project_id is present, with source deletion cascading its
owned unpublished planning data; retained active projects remain independent.
Append DemandPublicationVersion with source-version identity/hash, request key,
revision, actor/reason, source observation, cost-free metadata and missing reasons.
Append DemandLine rows keyed by component/assignment identity within the source:
capability, quantity/allocation, dates, model, continuity keys/evidence only.
Never accept rates/costs in the demand schema. Nullable unresolved quantity,
allocation or dates must not become zero or fabricated defaults. Manual skills,
level and continuity enrichment require explicit evidence and current-source CAS;
role/count/dates/allocation derive from immutable source staffing where present.
Scalar probability is descriptive, never a recruiting multiplier. Old source
versions stay immutable; current reads expose pending/stale publication instead
of claiming freshness from an older version. 0058 retains sourcing/event/rule
reservation. No new release or staffing-policy approval is implied.

09:36 UTC explicit plan-publication API increment: Delivery/SystemAdmin may
POST /people/demand/publications with source-version and publication-version
CAS, idempotency key, written reason and evidence-backed capability enrichment.
Source-plan row locking serializes publication with plan revision. Request-key
replay returns its original publication, not a new revision. Unknown/removed/
foreign workforce identities cannot confer continuity. GET /people/demand
allows cost-free organizational HR/Delivery/Finance/CEO/Admin reads and owned
Sales portfolios; no named continuity identifiers outside HR/Admin. Pending or
stale source publication returns explicit missing state and no old fresh lines.
This endpoint lists source demand, not globally allocated supply or a sourcing
draft. Those connected outcomes and retained delivery projects remain required.

10:12 UTC allocation increment7f98459: /people/demand/allocation computes across
authorized runtime/test-source population before owner/account display filters.
Stable demand identity is UUID5(publication_id,line_key), not the component-only
key reused by different plans; managed commitment assignment_key uses this ID
for explicit continuity. Named matches remain HR/Admin-only; other readers
receive scoped counts without named bench or foreign account labels. Missing
competing sources mark the result incomplete even when hidden by display scope.
Inactive/nonselected sources do not create pending recruiting demand. Unresolved
empty staffing is not zero, and exact-arithmetic failure returns explicit
incomplete output, never rounded totals or a silent successful zero. Freshness
is measured import age, not a live-connector or approved-age-threshold claim.
This increment covers forecast plans and managed supply only; retained delivery
projects, sourcing revisions/rules/events/snapshots and full connected T22/T23
remain open. Manual enrichment is preserved when omitted, with new evidence
required for changed nonempty capability/continuity; source facts remain derived.

10:43 UTC0058 sourcing persistence increment (FC-07/10/12,T22/23/24/28):
HR/Admin owns versioned sourcing lead-time rules by exact skill/location, with
explicit wildcard skill support. Multiple matching skills use the greatest
lead time, never the shortest; an exact skill rule overrides a wildcard at that
location. No matched rule means missing lead time, not an invented date. Starter
45-dayUS/30-dayIndia values are suggestions requiring explicit saved settings.
Dates subtract calendar days from the actual first gap date; zero staffing gap
does not become new hiring demand. Continuing and incremental quantities remain
separate. Sourcing is a proposal, never a reservation, hire or communication.

Lead owns0058 rule root/immutable versions and sourcing draft/immutable versions.
Scope is tenant/environment/server-derived test provenance. Rule writes have
CAS, request-key replay, actor/reason and audit in the same transaction. Drafts
bind a DemandPublicationVersion, rule version and global allocation watermark;
identical inputs are idempotent. New timing/probability/staffing/source inputs
append history; stale publication refuses refresh rather than publishing old
demand as fresh. Draft snapshots are cost-free and contain no named matches.
Worker/event refresh is a separate0059 increment, not claimed from manual API.
0058 downgrade refuses populated history; real PostgreSQL roundtrip/locks and
source deletion cascades must be proved. Retained project scope and conversion
lineage remain required and separately unresolved, not solved by sourcing.

10:56 UTC sourcing HTTP/UI contract: HR/Admin only GET/POST
/people/sourcing/rules. GET returns state(unconfigured/configured),id|null,
revision|null,rules[{skill,location,lead_days}], optional actor/time/reason. POST
adds expected_version_id|null,request_key,reason; returns configured version.
GET /people/demand now includes publication_id|null alongside existing source
and publication version IDs. GET /people/sourcing/drafts?publication_id=UUID
returns items (latest first),current_version_id|null,state(missing/current/stale).
POST samepath requires publication_id,expected_demand_version_id,
expected_rule_version_id,expected_draft_version_id|null,request_key,reason.
Each draft result includes id,draft_id,revision,demand_version_id,rule_version_id,
source_watermark,snapshot,reason,created_by,created_at,is_reservation:false.
Snapshot has title,probability,lifecycle,source_version_id,source_url,complete,
missing,calculation_version,is_reservation:false and rows with id/account_id/
plan_id/title/account_name/source_url/role/skills/level/location/timezone,
quantity/retained_quantity/incremental_quantity/matched_quantity/gap_quantity/
continuity_gap_quantity/incremental_gap_quantity,gap_fte(string),start,
end_exclusive,sourcing_by|null,missing. No named matches or financial fields.
Visible UI must preserve drafts on409 with explicit reload and current CAS;
stale source cannot prepare a current draft. Rules begin empty/unconfigured;
lead times require manual HR judgment because documents do not establish a
recruiting SLA. This is the written justification for those manual values.

11:10 UTC retained project source authorization increment (S21-01,DG-06,FC-07,
CO-09): new release baselines may add immutable server-derived source_scope
beside copied canonical commercial evidence. Require matching commercial
snapshot tenant/environment, exact GM/SOW/deal lineage, original account/owner,
and authoritative fixture issuance reference when applicable. Revalidate that
append-only grant, issuer, participant and expiry on reads even after parent
detachment; a test boolean alone grants nothing. Missing old provenance stays
unresolved, never adopted into the current runtime or guessed as real. Existing
immutable baselines are not rewritten. Scope authorization is independent of
the later role/portfolio projection. Do not use retained Projects list fallback
as People authorization; do not restore deleted SOW revenue. Lead retains
publication/allocation/conversion-lineage integration and schema ownership.

11:34 UTC retained demand publication increment: reuse0057 project_id ownership,
never disguise a project as a ForecastPlan. Cost-free source DTO adds source_id,
source_kind and nullable project_id alongside legacy plan_id (null for projects).
Project source version is the immutable captured GM UUID; source hash is the
validated frozen canonical evidence hash. Delivery/Admin publishes capability
enrichment with the same CAS, replay, evidence and audit guarantees as plans.
Read authorization uses project_scope_allowed before owner/account projection;
archived projects are not active demand. Deleted commercial parents do not
delete project publications. Frozen original account/owner IDs remain source
identity after live foreign keys detach. Missing legacy scope is never adopted.
This increment does not restore financial schedules or infer staffing conversion
from money fractions. Explicit conversion coverage and automatic events remain
separate required work; no complete demand claim before their integration.

12:02 UTC staffing conversion contract (FC-05/07,T21/22/23): financial fractions
never multiply people. An explicit cost-free coverage maps distinct zero-based
plan demand slots to distinct committed project demand slots for inclusive dates.
Both sources require same account/capability/location/timezone/allocation and
compatible service bounds. Reject overlapping reuse of either endpoint slot,
unknown identities, noninteger slots or quantities and tentative replacement.
Coverage subtracts only mapped plan slots in covered intervals; project demand
stays full. Retained identities correspond to the first named slots and remain
intact for uncovered slots. Keep stable demand IDs and continuity credits.
Pure contract: DemandCoverage(plan_id,project_id,plan_slots,project_slots,start,
end), validate_coverage(demands,coverages), apply_coverage(demands,coverages,start,
end) -> tuple of residual Demand objects. IDs here are demand-line IDs, not
parent entity IDs. Lead persists source-version-bound mapping, actor/reason,
CAS/audit and trusted access; no worker invents mapping or derives it from money.

0059 is reserved by lead for staffing-coverage roots and immutable versions;
automatic sourcing events follow in0060, not on a parallel Alembic branch.
Root identifies scoped plan-publication/project-publication pair. Version binds
both publication-version IDs, explicit line keys/slot arrays/date ranges,
reason/actor/request key/hash and increasing revision. Empty mappings explicitly
clear coverage through a new revision. Deleting the plan publication cascades
its coverage; deleting a SOW cannot remove retained-project demand publication.
Source revision changes make existing coverage stale until confirmed again.
Global allocation incorporates coverage before account/owner display filtering
and includes mapping versions in the sourcing watermark. Source completeness
and stale coverage remain explicit; no cached map is silently rebound.
Delivery/Admin writes with plan then project source locks, mappingCAS, matching
account/trusted scope and audit in one transaction. A monetary conversion alone
does not authorize a staffing mapping. API controls and realPG/concurrency/
deletion/browser proof are required before marking this capability implemented.

Coverage HTTP contract: Delivery/Admin POST /people/demand/coverage body has
plan_publication_id,project_publication_id,expected_plan_version_id,
expected_project_version_id,expected_mapping_version_id(nullable),request_key,
reason,mappings[{plan_line_key,project_line_key,plan_slots:[zero-based ints],
project_slots:[zero-based ints],start_date:ISO,end_date:ISO}]. No money fields.
Response is {id:rootUUID,version_id,revision,plan_publication_id,
project_publication_id,plan_version_id,project_version_id,mappings,reason,
created_by,created_at,state:current|stale,is_reservation:false}.
GET samepath requiresplan_publication_id, optionalroot_id,page(default1),size50.
Withoutroot_id returns current version per linked project; withroot_id returns
immutable history newestfirst. Envelope {items,current_version_id(nullable),
is_reservation:false}. Read followsDEMAND_READ plus authorizedsource/portfolio;
no named identity or costs echoed. UI component receives plan and available
DemandSource[] and onSaved; use source-kind project options only, exact source
versions and currentmappingCAS. Prefill matching line/date ranges and explicit
consecutive slot/count controls (one-based positions shown, zero-based wire).
Multiple mapping rows support nonconsecutive slots and partialdates; server
validates capability/continuity. Preserve conflicts/drafts, historyselection
never changes currentCAS, explicit emptyrevision clearscoverage withreason.

Manual-field justification: the count of staffing slots actually replaced is
not derivable from equal source quantities, win probability or monetary scope.
Prefill matching capability lines, one-based first positions and intersecting
dates; the reviewer explicitly chooses the replacement count and reason before
save. Do not silently treat every matching person as converted. This is an
intentional manual business assertion, not an unfilled derivable source field.

Recovery clarification: an archived project is not available for new staffing
mappings, but its immutable mapping history remains readable under the same
trusted source/portfolio scope. An explicit empty revision can clear an existing
mapping using the current mapping CAS and publication-version IDs belonging to
the exact roots (historical versions are allowed for this nonasserting removal).
No bypass of role, tenant, test classification or source provenance is allowed.
The editor lists unavailable mapped project identities as historical choices;
only reasoned clearing/history is enabled, never a new mapping. Empty roots
cannot be created as a substitute for a real mapping.

## Same-Document Extraction Replay

FC-09/T24: reuse existing field provenance/status and confirmation audit, not a
parallel extraction service. Re-extracting the exact same immutable document
must preserve explicitly human-confirmed field envelopes, including accepted
unchanged values. Legacy/default manual provenance alone is not confirmation.
New unconfirmed candidates still undergo normal strict validation; a failed
attempt stays visibly failed/manual-required without erasing prior confirmed
values/evidence. Never mark a failed attempt complete merely because protected
fields remain. Compare downloaded bytes' SHA256 with the version's recorded
document hash; mismatch is a source-change conflict, not a retry, and may not
transfer corrections silently. Approval/submission/signature immutability gates
still apply. Confirmed corrections carry only within the same document version.
Source-change proposals and a versioned seven-profile held-out corpus remain
separate outstanding work. A owns existing sow_extract.py replay/merge blocks,
sow.py reextract gate/docstring only, new focused override tests and lane report;
lead owns migrations, upload pipeline integration, all deployment and shared tests.

## Sourcing Automation Increment (0060 Rules; 0061 Outbox Reserved)

FC-07/10, T22/T24/T28: this increment connects source changes to existing
publication/allocation/sourcing services, not another calculation implementation.
Other automation domains remain outstanding and may not be marked complete by
this sourcing-specific increment. Lead owns0060 and all emitters/worker wiring.

Persist tenant/environment/test-classified rule roots with immutable versions,
request-key/hash, actor, reason and CAS. Initial domain is `sourcing_refresh`;
SystemAdmin configures enabled/disabled and the source scope, with server-side
source authorization retained at execution. The initial default is unconfigured,
not silently enabled. No generic rule can alter approval policy, quote/sign/mail
clients, reserve people or authorize hires. Existing upload extraction behavior
is unaffected by this initially sourcing-only domain.

Persist idempotent outbox jobs in the same transaction as relevant source
changes: plan timing/probability/scope/staffing/lifecycle, published retained
delivery staffing, managed supply, sourcing lead times and explicit coverage.
Use source/version/rule revision identity, not mutable titles. Workers read the
current rule and current actor authorization before side effects; a disabled
rule must stop execution, not merely hide UI. Deleted parents cascade/cancel;
stale versions are superseded explicitly, never overwrite a newer publication.

Reuse existing publication and draft idempotency APIs with job-derived request
keys. A crash after a service commits but before job completion replays the same
version rather than duplicating a publication/draft. No cached allocation is
treated as current: recompute global-before-filter and preserve the watermark.
Incomplete capability/supply remains a visible review state, not invented data.
Sourcing history records changed probability/dates/quantities/nonrenewal effects.

Expose persisted job status, attempts, next retry, last success/error and source
identity through cost-free authorized endpoints. Claim using PostgreSQL locks;
failure backoff is recorded, and bounded failures remain visible. Add a separate
real worker-process journey and crash/replay tests, plus rule-disabled and
revoked-role/source tests. Unit tests alone do not establish event integration.
Notification delivery additionally respects existing user preferences; a job
must never send financial details to a role that cannot read them. Typed HTTP
payloads and ownership must be committed before dependent UI authoring.

0060 typed rule API: SystemAdmin GET/POST `/people/sourcing/automation`, GET
`/people/sourcing/automation/history?page=1&size=50` (size1-200). POST requires
`expected_version_id: UUID|null`, strict boolean `enabled`, normalized nonblank
`request_key` and `reason`; `source_scope` is the literal `authorized_sources`.
No domain selector or grant expansion is accepted. Result has state
unconfigured/configured, fixed domain sourcing_refresh, enabled, revision/id,
scope, actor/reason/date; history adds current_version_id and newest-first items.
409 preserves current state; enable/disable is an append-only revision. The
source scope means sources currently authorized to the configuring actor under
the runtime tenant/environment/test classification, rechecked when processing.
Rule storage/API alone is not functioning automation or an FC-10 completion.

0061 worker transaction refinement: let existing publication/draft services
participate in the caller transaction (default standalone commit unchanged).
Keep the job claim, current rule lock, source permissions/publication, refreshed
draft and completion in one transaction. A process crash rolls all effects back;
job-derived idempotency keys additionally protect replay. Rule mutation waits
for an in-flight job; once disabled commits, no subsequent job may proceed.
Do not use a lease that can expire during an unfenced side-effect commit.

Job operations: SystemAdmin GET `/people/sourcing/automation/jobs?page=1&size=25`
(size1-100), POST `/people/sourcing/automation/jobs/{id}/retry` with exact
`expected_attempts` integer and normalized nonblank `reason`. Scoped results
contain source/version/event identities, status, attempts, error, retry time,
completion, result version and can_retry; list includes last_success_at. No
financial or named-person payload. Explicit retry permits failed/review states
under the same current enabled authority, with fewer than5attempts; it never
resets attempts. Terminal exhausted jobs require an actual corrected source/rule
event, not a budget bypass. Stale retry is409; foreign identity404. Frontend
typed contracts are web/src/api/sourcing-automation.ts, committed before UI.

Pending refresh coalescing: while holding the current automation root lock, a
worker's publication may reuse an already-pending job for the same rule, source
and source version. That pending job computes from the current global population
after acquiring the same root lock. Do not coalesce completed/failed/review jobs,
different source versions, or ordinary external events without this lock.
Prioritize the directly changed plan version before dependent global refreshes,
so dependents do not produce a redundant pre-publication snapshot. Completed
history and event/audit identities remain immutable; source authority, CAS and
global allocation watermark validation remain mandatory.

Released-project creation emits a sourcing event in the release transaction,
only on first creation. Select the rule's fixture classification from validated
captured project source provenance, never the releasing reviewer's group labels.
Use the rule creator's current persisted authority for population and worker
checks. Legacy unresolved provenance does not enable automation. Missing skill
or level stays visible as review-required staffing; no capability is invented.
Later explicit capability publication produces a new reviewed draft revision.

## Re-extraction Conflict Review Increment

FC-09/S21-18, T16/T24: reuse existing same-document conflict metadata and audit;
no new extraction engine or invented confidence. Owner/authorized deal editor
or SystemAdmin may GET `/sow/versions/{id}/extraction-conflicts` and POST
`/sow/versions/{id}/extraction-conflicts/{field}`. Read returns items containing
field, current/candidate provenance envelopes and review_token. POST requires
review_token, decision (`keep_confirmed` or `accept_candidate`) and normalized
nonblank reason. Token hashes document identity, current field, candidate and
extractor revisions. Source/version locks and token CAS reject stale decisions
with409; immutable/submitted versions remain immutable. No read grant expansion.

Keep preserves the confirmed envelope exactly; accept keeps candidate evidence
and stamps explicit human confirmation. Both audit the reviewed alternatives,
reason and chosen value in the same transaction, then remove only that conflict.
Clear conflict-derived manual_required only after the last conflict; unrelated
provider failures must remain visible. Generic edits do not dismiss conflicts.
Both scope-completion and legacy submission must refuse unresolved conflicts.
Typed UI shows the two values/evidence and explicit decision/reason per field;
review doesn't automatically submit, approve or change policy. Defer/dismiss,
bulk noncritical review and the broader exceptions queue remain separate scope.

Currency contract reconciliation (S21-04/18, FC-09): v3's missing/ambiguous
currency rule supersedes the inherited `_default_currency` house-USD behavior.
Do not fill absent source currency on confirmation reads. Missing currency and
unconfirmed defaulted currency block scope completion; an explicit human field
confirmation resolves that gap. Preserve already-confirmed historical currency
envelopes; reporting currency configuration never supplies contract evidence.
Existing fixed-fee cost test retains every assertion and supplies explicitUSD
as a prerequisite so it continues to isolate cost-vs-bill-rate behavior.

## Supported Pipeline Fixture Projection (T17 / CO-05)

Accepted implementation contract from lanes/pipeline-fixture-boundary.md:
Pipeline read population may additionally include `source=sow_upload` deals
whose exact IDs have passed existing server-side fixture grant validation for
the current test participant, tenant, environment, expiry, issuer and owner.
This internal capability defaults empty, is never a query/body/saved-view field,
and must reach every list/detail/summary/client/facet/search/export population
before pagination or aggregation. Existing business filters still apply.
Normal users and unvalidated callers get no fixture rows or aggregate leakage.

Keep source classification, null external IDs, issuance/approval/release guards
unchanged. Connector enumerators/linkage/writeback remain strictly HubSpot-only.
Response/UI source provenance must say local test fixture, not imply CRM data.
No fake pipeline/stage/BU facts. Tests must cover valid and invalid grants,
unauthorized participants, normal users, exact IDs/counts, and unchanged release
provenance. A connected local journey through this projection is not live
HubSpot sync/canary, real Cognito/mail or staging acceptance. No migration or
infrastructure approval is implied or waived.
# Typed Signatory Extraction (2026-10-02)

Provider prompt `sow-v5-typed-signatories` emits a dedicated signatories entry:
array of `{name: string, role: string|null}` or null, with evidence and status.
Personal names are copied separately from explicit organizations/roles. Local
provider validation rejects untyped or empty identities; historical stored
identities remain readable. Approval/signature name matching is unchanged.
This addresses observed real-provider identity/organization conflation, not a
claim that held-out extraction quality or the full journey has passed.
# Shared OCR Evidence Contract (2026-10-02)

FC-09 primary bound upload, unbound/bulk upload and re-extraction must share a
document preparation path. Digital PDF/DOCX keeps existing block/page evidence.
Low-density PDF uses the existing Textract integration, preserves original page
numbers and table row/column text, and surfaces provider/empty/unreadable failures
as explicit manual review without inventing commercial values or losing the file.
No document classification or client matching is based on fabricated OCR text.

Adapter addition: `TextractClient.extract_document(pdf_bytes) -> DocumentText`
with page-indexed blocks; existing `extract_text` remains a compatibility API.
Use pypdf (existing dependency) to split a supported multipage PDF into individual
PDF pages for sequential AnalyzeDocument calls with FORMS and TABLES. Preserve
original numbering; reject encrypted/unreadable/oversized per-page input before
provider calls; all-or-review, never silently return a partial document after a
page failure. No new S3 staging bucket, async cloud job or infrastructure mutation.
Provider text is untrusted. Table locators remain evidence, not computed prices.
API call payload/response tests are deterministic boundary tests, not live proof.
A small synthetic live scanned/table sample is required separately before any
claim of OCR operational readiness. Existing extraction dedupe/attempt contract
remains outstanding, not silently satisfied by this adapter.

AWS primary references: https://docs.aws.amazon.com/textract/latest/dg/sync.html
and https://docs.aws.amazon.com/textract/latest/APIReference/API_AnalyzeDocument.html
(read2026-10-02). Synchronous PDF is single-page, maximum10MB; existing ten-page
adapter comment/constant is incorrect. Own original document upload limit remains.

Ownership: new isolated OCR worker owns only integrations/textract.py and new
test_s21_textract_evidence.py plus its lane report. Lead owns shared preparation
service/callers and any subsequent persistence migration; Pipeline worker remains
separate. One heavy runtime at a time; no worker provider/network/infrastructure.

## T40 Approval Card Workflow (2026-10-02)

CO-04 retains its original definition: distinct current in-review SOW packages,
not deals or reviewer assignments. `GET /approvals/packages?status=in_review`
will expose the canonical live/current package population with existing page,
size,total response shape. In-review means pending_delivery_hr,
pending_finance_legal or pending_ceo_exception; newest nonvoided package per
live SOW, excluding archived/deleted SOW/deal/client and superseded packages.
Two separate live SOWs under one deal count twice. Owner/assignment/read-role
visibility and valid server-issued fixture isolation both apply before counting
and pagination; a forged label/tag is never authorization. Unissued siblings of
a valid fixture remain inaccessible. Closed deal stage alone does not redefine
an in-review package as approved. No cost exposure or approval mutation.

Command Center obtains its scalar from that endpoint's total and opens
`/sows?status=in_review`. Destination uses the identical endpoint/scope, loads
every page without a100-row truncation, and rejects inconsistent pagination
rather than fabricating a total. Failure is unavailable, not an assignment-array
sum or fake zero. Existing sales-stage Pipeline chips remain unchanged.

Worker ownership: `/Users/srikanthparimi/OfficeApp/dealgate-s21-approval-card`,
branch `s21/approval-card-population`, base5a5c42c849ecb3807d0816beec62c5fd49bf6782.
Own ONLY `api/app/services/approvals.py` list/filter helpers,
`api/app/routers/approvals.py` list endpoint, new `api/tests/test_s21_approval_card.py`
and `docs/s21/lanes/approval-card.md`. No existing approval transitions or schema
changes. Lead owns frontend, browser/PG fixture setup, integration and runtime.
One light worker initially; no second worker or installs/heavy runtime while
lead Watching proof uses the slot. Host19:58 has~145MiBfree/~1382MiBcompressor,
16GiBdiskfree: author-only concurrency, not another test process.

T40 snapshot refinement: canonical response adds `population_revision`, SHA256
of authorized ordered package identities/status/source version plus viewer/filter
context. Card passes it to destination; every later page sends it back. Any
population change, including an equal-count replacement, returns409 and requires
explicit refresh. No automatic retry or mixture of revisions. Existing exact
status APIs retain compatibility with nullable revision. No database migration.

## T09 Isolated Filtered-Population Proof

Use a dedicated local synthetic CRM-mirror database `s21_filter_<32hex>` on
literal127.0.0.1:55421 with tenant equal to database name. Never invent CRM facts
on issued sow_upload fixtures or reuse retained s21_journey for mirror seeding.
Lead alone creates/migrates/runs/drops the scratch runtime with ownership proof.
No live HubSpot calls. Fixture declares its synthetic provenance and computes
expected identities/counts/money from literal authored data, not reader outputs.

Worker governance owns ONLY scripts/s21_filter_fixture.py and
docs/s21/lanes/filter-fixture.md in separate tree dealgate-s21-filter-fixture,
branch s21/pipeline-filter-fixture, basebd188a3. No runtimes/install/migration;
seed helper refuses nonempty business tables. Lead owns Pipeline UI/client/tests
and connected browser. QA read-only assessment finished. One light author plus
lead;21:05 memory~40MiBfree/~2GiBcompressor prohibits a second heavy runtime.

Saved-view selection replaces previous predicates, preserving page size only.
Pipeline export uses the identical shared serialized filter set and authenticated
request, excluding pagination. CSV exports all matches; failures remain visible.
T09 requires exact three-page IDs, positive owner/BU/stage selection, matching
clients/chips/summary/export, remove-one-chip, reload/Back/saved-view, zero set,
and delayed genuine older response fencing. Source-parity/staging remain separate.
