# People Demand Implementation Contract

Status: proposed, not implemented. FC-07, related FC-08, T22 and T23 remain
missing pending code and real application/database/worker/import proof.
Read-only investigation on `s21/forecast-overview` after `a72687d`; no tests,
runtime, migrations, provider calls or production edits in this follow-up.
Budget: 15 minutes. Lead alone assigns migration numbers and integrates.

## Existing Truth and Reuse

| Exact path / object | Reuse and limit |
| --- | --- |
| `api/app/models/forecast.py`: ForecastPlan, ForecastPlanVersion | Tenant/environment, account/deal, owner, immutable version, scope, lifecycle/probability, assumptions and commercial inputs already persist. Attach demand to this version; do not invent another plan identity. |
| `api/app/models/forecast.py`: ForecastConversion | Existing plan-to-signed-GM relationship. Reuse identity but not `scope_fraction` as a staffing ratio: money conversion cannot determine which people transfer. |
| `api/app/services/forecast_plans.py`: PlanInput, save_plan, _plans, runtime | Optimistic versions, source binding, idempotent request/hash, tenant/environment and account scope patterns. `_plans` currently excludes HR: a dedicated demand permission path is needed; do not grant HR unrestricted commercial inputs. |
| `api/app/models/gm_model.py`: ResourceLine | Role, seniority, location, dates, allocation and optional person_name for legacy signed staffing. Contains rates/costs, no stable person ID, skills, quantity or availability. Never join people by display name or infer quantity from hours. |
| `api/app/gm/calendar.py`: StaffingAssignment, WorkCalendar | Canonical quantity, allocation, location/timezone, dated schedules, assignment/source/component identity. Missing skills, level and confirmed person/team continuity links. Read these inputs but never copy their cost/bill rates into HR responses. |
| `api/app/models/project.py`: Project | Signed release baseline and retained delivery evidence. Use active signed staffing as committed demand; exclude drafts/obsolete versions and preserve actual delivery records after SOW deletion. |
| `api/app/models/user.py`: User | Authentication identity only. It is not a workforce directory or an available-person list. |
| `web/src/pages/v2/settings/PeopleSection.tsx` | Existing People & access is users/roles/groups/delegations, not recruiting. Add a genuine role-accessible People planning view; do not hide it behind admin-only settings. |
| `api/app/services/actuals_import.py` | Reuse managed-import validation, provenance, immutable correction and audit design; no reuse of finance row tables for people. `models/import_batch.py` is SOW-document import, also unsuitable for availability rows. |
| `api/app/models/notification.py`, `services/notifications.py` | Existing outbox and NotificationSetting category/channel preferences. Use `queue_notification`; register the new category. Existing outbox has no event uniqueness: guard enqueue through a unique demand event. |
| `api/app/audit.py`, `api/app/workflow/` | Transactional audit and authorized state transitions. Forecast changes must not directly reserve staff or create hiring authorization. |

No workforce directory, availability calendar, sourcing request or HR connector
was found in this checkout's models/routers. The complete smallest fallback is
a validated managed import, visibly labeled with source and freshness.

## Persistent Additions

Proposed new `api/app/models/people_planning.py`, not an alternate financial
engine. Every identity/current selector includes tenant and environment. Store
Decimal allocation/FTE as NUMERIC, expose strings. Dates require timezone and
explicit inclusive/exclusive boundaries, no inferred 160-hour months.

1. `PeopleImportBatch`: id, source system, request key/hash, actor, imported_at,
   source_as_of, status, validation errors and supersedes reference. Whole-file
   reject on errors; identical retries return the same batch, conflicting key
   returns 409. Corrections append, never destroy prior availability evidence.
2. `WorkforcePerson` identity: stable source-system/person-key unique within
   tenant/environment, display name and optional authenticated-user link.
   `WorkforceVersion`: immutable batch-linked skills (canonical keys), role,
   level, location/timezone and effective interval. `WorkforceCapacity` rows:
   dated gross capacity/allocation and dated committed/reserved assignments
   with authoritative project/source identity, roll-off and status. Explicit
   payload basis must be gross capacity plus assignments, not unexplained
   already-net availability; avoid subtracting commitments twice.
3. `DemandPublication`: stable identity per source type and plan ID (or signed
   GM identity) with immutable versions keyed by source version + demand hash.
   Publication records actor, source evidence, source freshness, version and
   policy revision. `DemandLine`: stable demand_line_key across revisions,
   component/assignment key, role, skill keys, level, integer quantity,
   Decimal allocation, location/timezone, start/end, delivery model, source
   plan/version/account/deal, owner, lifecycle, probability and probability
   source. Missing fields remain explicit unresolved reasons; no invented
   skills or headcount. Rate/cost fields are not part of this projection.
4. `DemandContinuity`: explicit demand-line/person-or-team/assignment linkage,
   confirmed retained quantity and incremental quantity, effective dates,
   evidence and confirmer. Conversion coverage maps demand lines/quantities
   to signed assignment identities; monetary fractions never scale people.
5. `SourcingDraft`: one stable request per publication identity and demand-line
   key, never one per event. Immutable `SourcingDraftVersion` references source
   publication version, quantity, allocation, dates, skill/location needs,
   continuity, sourcing-by date, reasons and previous revision. Status only
   draft/withdrawn/superseded at planning endpoints. A new probability/start/
   headcount/nonrenewal revision updates the same draft identity and history.
6. `PeoplePlanningRuleVersion`: effective, auditable lead-day rules by skill
   and location plus allocation-policy version. Seed 45 US / 30 India as
   explicitly labeled configurable starter values only. Missing rule is
   unresolved. `DemandEvent` uniqueness on publication version + event kind
   guards transactional job/outbox enqueue and restart-safe retries.

Avoid a separate durable table for every chart: compute month projections and
global matching from these versioned inputs. Persist a `DemandMatchSnapshot`
with selected source-version watermark, allocation-policy/rule version and
immutable candidate allocations when generating sourcing drafts. Identical
watermark yields identical results; changed supply invalidates old matches.

## Matching and Lifecycle

Perform matching server-side in proposed `api/app/gm/demand.py`, pure and tested,
or adjacent domain module if repository policy requires. Financial arithmetic
continues to use existing `api/app/gm`; do not derive recruiting demand from
probability-weighted revenue or cost. Flatten hybrid staffing by canonical
assignment identity, not by repeated component appearances.

Use dated intervals split at every start, end, capacity change and roll-off.
Match exact confirmed capability, level, location, timezone compatibility,
dates and allocation. Missing compatibility data means unresolved, not match.
Subtract confirmed commitments/reservations exactly once, then allocate each
remaining person's capacity across the entire trusted tenant portfolio before
applying account/owner display filters. Restricted scopes see only authorized
demand; hidden competing work may appear only as unavailable capacity, not as
another account/person's details. Never recalculate a fresh bench per account.

Candidate matching is tentative and does not write reservations. Deterministic
priority proposal: confirmed committed shortfalls first, then tentative demand
by sourcing-by/start and stable source/demand IDs. Make priority explicit and
versioned; business confirmation is required before claiming it is company
staffing policy. A tie-break is not automatic hiring approval.

Resource scenario switching changes financial context, not demand quantity.
Show tentative and committed separately in every scenario; distinguish imported
reserved/hired staffing evidence. An explicitly selected scenario-group option
contributes to a candidate matching run; show competing alternatives separately,
not as cumulative new hires. Unknown selection is unresolved.

Month output includes active named/count demand, peak concurrent headcount,
dated intervals, Decimal peak FTE, any calendar-average FTE with explicit
denominator, retained/incremental quantities, matched/unmatched allocation and
freshness. Do not add sequential teams into one concurrent month headcount.
Two half-time roles remain two role slots at total 1 FTE; a single suitable
person may cover both only when their dated allocations fit and requirements
permit. A continuing six-person team remains six required people, six retained,
zero incremental hires; missing confirmation is continuity risk, not free bench.

## API, UI and Permissions

Proposed `api/app/services/people_planning.py` and `api/app/routers/people.py`:
`POST /people/imports`, `GET /people/imports`, `GET /people/availability`,
`GET /people/demand`, `POST /people/demand/publications`,
`POST /people/demand/{id}/sourcing-draft`, `GET /people/sourcing-drafts` and
`GET /people/sourcing-drafts/{id}/history`. Versioned lead-rule reads/writes use
the existing settings service pattern. Every mutation takes expected version,
request key and written reason; schema forbids extra reserve/hire fields.

Demand list/month aggregates/export use one filter and one global allocation
watermark. Include named account/source, deep link, source version, probability,
status, model, dates, skills, headcount/FTE, gap, sourcing-by date, continuity,
freshness and missing reasons. Positive changes return persisted IDs and history.
Workers consume durable demand events after plan version commits and signed
conversion/release; obsolete/deleted source events cannot recreate live demand.
Nonrenewal withdraws future drafts but preserves history and current obligations.

Permission proposal for lead validation against blueprint: HR/SystemAdmin own
managed workforce imports/rules and sourcing drafts; Delivery publishes scoped
demand; Finance/CEO read appropriately scoped planning; Sales reads only owned
planning summaries, not named bench details. Existing named-cost HR permission
in `services/redact.py` must NOT leak into recruitment: return an allowlisted
cost-free demand schema for every recruitment role, including HR. No new
Recruiter role is assumed. Never broaden existing financial route permissions
just to make People work. No endpoint authorizes reserve/hire/client messages.

Add `web/src/pages/v2/PeoplePlanning.tsx` and `web/src/api/people.ts`, connected
from Forecast Resource demand and role-appropriate navigation (lead-owned shared
wiring). The same persisted publication appears in Forecast and People; separate
UI copies are not separate systems of record. Inline import validation, demand
correction, sourcing history and freshness must be usable, not static notices.

## Independent T22/T23 Oracle

Synthetic Company X assessment: 1-28 October 2026. Planned delivery:
1 November 2026 through 30 April 2027, probability exactly 0.70. Two US
engineers and five India engineers, all allocation 1.00 with confirmed skills,
level and separate timezones. With no supply, each active month shows headcount
7, US 2, India 5, FTE 7, gap 7. Expected/Committed/Upside selection must not
produce 4.9 recruiting people. Financial committed may exclude unsigned revenue;
the tentative team remains visibly seven. With confirmed starter lead rules,
US sourcing-by is 17 September 2026; India is 2 October 2026. Moving start to
1 December shifts dates to 17 October and 1 November respectively, without a
second sourcing request. Update end explicitly as part of the revision.

Two simultaneous compatible one-person, allocation-1.00 opportunities and one
person with gross capacity 1.00: exactly one candidate match total, one gap;
account A + account B cannot each show their own full match. For two 0.50
allocation roles the same person can cover both: two role slots, one matched
person, 1.00 FTE, zero allocation gap. If that person rolls off a committed
1.00 assignment on 15 November, availability begins 16 November; no match may
cover 1-15 November. Show dated unmet allocation even if a month summary is used.

Six-person extension: six linked continuing assignments, unchanged quantity
and allocation -> six retained, zero incremental. Seven-person extension ->
six retained plus one incremental, assuming dates/skills permit. Partial signed
conversion of three identified roles -> three committed plus four tentative,
not ten total and not seven scaled by a revenue fraction.

T23 real proof: create/import supply; publish versioned demand; open actual
People view; create draft; revise start/headcount/probability; restart worker;
replay identical and stale events. Assert one stable draft identity and exact
history, updated dates/gaps, persisted rows and audit/outbox counts. Denied
roles, cross-tenant/account IDs, CSV and deep links must not expose costs or
named hidden supply. Attempts to reserve/hire fail without side effects.

## Dependency Order and Decisions

1. Lead confirms role scope, skill/level matching taxonomy, calendar versus
   business lead days, priority tie-break and timezone/location compatibility.
   Until then exact-match capability and explicit unresolved states are safe;
   do not invent equivalence or promise allocation fairness.
2. Lead reserves the next available migration AFTER `0054` (candidate `0055`
   only if still free), checks one Alembic head and writes additive/reversible
   tables with composite uniqueness, optimistic version and query indexes.
   This document does not reserve or create a migration file.
3. Implement import/provenance and demand publication, then pure interval
   matching/oracles, transactional sourcing versions/events, permissions.
4. Wire the real People view and Forecast Resource demand; connect plan
   revisions/conversion/release/deletion workers and preference-aware alerts.
5. Independent T22/T23 integration/browser/export/concurrency tests and actual
   restart proof; only then update coverage. No unit count closes acceptance.

Material ambiguities for the lead to record, not silently decide: an existing
HR connector may exist outside this repository; obtain its contract or use the
managed import fallback. Recruiting ownership is not a separate current role.
Lead-day business calendars and skill-level substitution are unspecified.
Monetary partial conversions require explicit role coverage mapping. Rules for
which equally eligible opportunity gets scarce bench need a versioned business
policy; deterministic order is merely a reviewable planning proposal.
