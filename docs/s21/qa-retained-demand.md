# Independent Retained Delivery Demand Audit

Baseline: `494ae2e86a7b48a358561568b7cdd7b49bf48740`.
Branch: `s21/qa-retained-demand`. Budget: approximately 15 minutes, static audit
only. This report is the sole owned file. Application code, migrations and
existing tests were read-only; no runtime, cloud, database or browser was used.
Findings below are source-derived, not executed reproductions.

## Binding Policy

- S21-01, directive lines 129-131: delete the SOW-owned graph and remove its
  schedule from active Forecast; retain projects with delivery activity,
  timesheets, invoices or actuals, detach and label the removed source. Keeping
  retained delivery demand must not restore deleted SOW revenue.
- CO-09, lines 662-665: parent/client deletion must preserve the same retained
  graph. Missing a HubSpot ID is not trusted test provenance. Cleanup requires
  authoritative tenant/environment/run ownership and cannot broaden deletion.
- DG-06, lines 264-268: handoff is once-only, carries the approved source and
  staffing, and receives effective amendments. Unsigned proposals cannot alter
  an active delivery commitment.
- FC-07, lines 298-303: full integer headcount, dated allocation and capability;
  one global capacity allocation; current commitments, continuing teams and
  release dates; separate incremental hiring need. Six unchanged extension
  people are six retained slots, not six automatic new hires. Sourcing lead times
  and rules are configurable, not invented defaults.
- Source deduplication, lines 123-124 and FC-05 lines 285-287: preserve signed
  authority, count economic coverage once, and represent partial conversion
  explicitly. A financial scope fraction does not identify which staffing slots
  or dates were contracted.
- `docs/s21/contracts.md:270-296`: existing 0057 publication identity supports
  exactly one plan or retained project; immutable source-bound versions and
  cost-free lines; evidence-backed enrichment; no implicit hiring/reservation.

## Findings At Baseline

1. **Canonical staffing is not frozen into the project.** There is no
   `ProjectBaseline` model/type in this revision. The persisted source is
   `Project.baseline_snapshot_json` (`models/project.py:57`). Its builder
   (`services/project_lifecycle.py:49-99`) copies legacy `resource_lines` but
   omits `commercial_inputs` and `commercial_snapshot`. Canonical commercial
   creation writes those two fields on GM and does not populate legacy resource
   lines (`services/commercial_models.py:117-137`). A canonical seven-person GM
   can therefore leave a project baseline with no canonical assignments/calendar;
   deletion then removes the GM. Legacy rows also lack canonical quantity,
   timezone, calendar and skills, so they cannot safely imply one complete person
   per row. Lead reports an uncommitted deep-copy correction plus two new tests;
   that correction and its test result were not independently inspected here.

2. **Retained identity is not an authoritative runtime scope.** Project has no
   tenant/environment/test columns. Deletion preserves original IDs, account
   name, owner and a boolean test classification, but not tenant/environment or
   the fixture grant/run (`services/deletion.py:617-624`). The existing retained
   Projects reader queries all retained rows and checks account fixture scope,
   or merely rejects test/orphan combinations when the account is absent
   (`services/projects.py:126-146`). An orphan real project has no tenant filter;
   switching runtime tenant does not exclude it in this branch. This reader is
   not a safe authorization adapter for a new People source. Commercial
   snapshots do contain server scope (`services/commercial_models.py:119`), but
   are absent from today's project baseline and contain no fixture grant.

3. **0057 is structurally ready, but the path is plan-only.** The publication
   model has project FK, unique project scope and plan/project XOR constraints
   (`models/people_demand.py:15-27`). `publish_plan_demand` locks only ForecastPlan
   (`services/people_demand.py:72-105`), and `_source_rows` enumerates only plans
   (`:171-219`). Allocation visibility, diagnostics and metadata likewise require
   `plan_id` (`services/people_allocation.py:19-55,69`). Adding a project writer
   alone will not make retained delivery participate in allocation. Do not
   fabricate a plan ID or clone a released project into an unsigned plan.

4. **Conversion lineage will be lost at detachment unless preserved first.**
   `ForecastConversion` keeps a plan ID, nullable GM ID and financial fraction,
   not project/staffing coverage (`models/forecast.py:123-132`). Deletion sets
   that GM ID to NULL (`services/deletion.py:629`). The retained record knows an
   original GM ID, but the nulled conversion no longer identifies it. Extending
   the plan-only population with projects without explicit surviving coverage
   can double count the same seven people, or let the old plan reappear after
   deletion. A monetary fraction alone cannot repair this.

5. **Copying canonical evidence widens an existing read-boundary risk.** Active
   Projects returns the entire baseline (`services/projects.py:101`), including
   legacy `hourly_cost` (`project_lifecycle.py:91`), and `/projects` returns the
   service output directly to roles including Sales/Legal (`routers/projects.py:11-28`).
   Such roles lack generic cost entitlement (`services/redact.py:52-54`). An
   authorized Sales owner can currently receive that active baseline. Retained
   rows instead gate it to Delivery/Finance/CEO/Admin (`projects.py:146`). Note
   the policy distinction: generic cost redaction includes HR, the retained gate
   does not. This audit does not redefine organization-wide HR entitlement.
   People demand is explicitly cost-free regardless. Lead plans to align active
   baseline gating with the existing retained gate; no correction is verified
   by this read-only report.

The signed Forecast adapter intentionally uses live approval-bound GM schedules
and checks their runtime (`services/forecast_plans.py:472-510`). Retained projects
are not an alternative financial input there. Their absence after SOW deletion
is consistent with S21-01, not a reason to reinsert deleted financial schedules.

## Bounded Implementation Contract

1. Freeze the approved canonical component tree and commercial calculation
   snapshot by value when capturing the delivery baseline. Preserve source,
   document/GM, policy, calendar, rate and calculation identities; no recalculation
   against today's policy/calendar. Keep the existing immutable baseline and
   append reviewed effective revisions instead of mutating signed history.
   Preserve structured business evidence, not the deleted uploaded document or
   file payload. Existing baselines without reconstructible evidence remain
   explicit incomplete sources; migration cannot invent staffing.
2. Establish immutable server-derived tenant/environment and real/test
   provenance before detachment. Validate live account/GM/package lineage while
   it exists; retain sufficient original account/owner and fixture issuance
   references for fail-closed authorization after parent deletion. Missing,
   conflicting, expired or foreign evidence never becomes ordinary real scope.
   A test flag distinguishes populations but does not grant a test participant
   access. Do not recreate a removed client/deal to authorize a retained project.
3. Reuse the 0057 project publication identity. Publish through Delivery/Admin
   permission, authoritative project/baseline lock, expected source revision/hash,
   expected publication version, actor-bound request replay and atomic audit.
   Replaying the same request produces the same revision; stale concurrent work
   fails without partial lines. A detached GM FK is not the current source
   version: the immutable retained baseline remains independently addressable.
4. Reuse canonical `project_staffing` validation and existing evidence rules.
   Project/plan sources need truthful typed source identity, working project
   source links, labels and cost-free line projection. Approved active delivery
   demand is committed, not tentative or probability-weighted; archived projects
   do not provide active demand. Unknown capabilities or legacy staffing stay
   visible with missing reasons, never a fabricated zero or complete match.
5. Allocate project and plan demand in one authorized runtime/test population
   before owner/account display filtering. Retain the existing versioned proposal
   ordering and no-reservation semantics. Missing hidden committed sources make
   the global result incomplete without exposing hidden IDs. Preserve named
   identity redaction for non-HR/Admin. Do not use UI filters as capacity fences.
6. Preserve explicit economic/staffing conversion lineage independently of
   deleted GM rows. Known same-source covered slots/periods occur once; unchanged
   extension slots remain continuity; incremental slots are separate. Never
   apply a financial fraction or win probability to integer recruiting demand.
   Partial coverage with no authoritative staffing mapping is unresolved, not
   guessed. Preserve the applicable original signed period until an amendment
   is approved and effective; a draft cannot replace it.
7. SOW/parent deletion and publication must share a durable serialization/fence
   boundary. After commit, retained project, baseline, publication and stable
   line/demand identities survive; ordinary source FKs detach and the source is
   labeled deleted. Keep imported same-source commitment identity valid. Late
   callbacks cannot recreate SOWs, financial schedules or duplicate demand.
   Rollback must leave both sides unchanged. Replay changes no retained history.
8. This increment is not sourcing drafts, source-change event/rule persistence,
   lead-time policy approval, financial recognition, a staffing reservation or a
   hiring workflow. Preserve those requirements rather than claiming them from
   a project-demand adapter.

## Independent Expected Outcomes

These are concrete future test oracles, not results from this audit. Use actual
release/publication/import/deletion services with isolated storage, plus a
separate PostgreSQL concurrency proof; do not seed a publication response.

| Case | Literal expected outcome |
| --- | --- |
| Canonical release | Source has 2 US + 5 India, allocation 1, 1 Nov 2026 through 30 Apr 2027, each location's explicit timezone/calendar. One released project retains both canonical assignments, quantity 7 and all six monthly 7-FTE requirements. Changing nested source objects after capture does not alter its baseline. Repeated release creates no second project. |
| Full conversion | An explicitly covered seven-slot plan and its approved seven-slot delivery source require 7 people / 7 FTE, never 14. The planned source remains traceable as covered, not silently deleted. Changing its descriptive 70% probability cannot produce 4.9 people or change the active delivery team. |
| SOW deletion | Give that project a real persisted activity/actual row, then delete the SOW. Exactly one retained project, unchanged baseline, existing project publication and stable demand keys remain; 2 US + 5 India still require 7 FTE within the approved interval. Source-deleted metadata is visible; removed SOW schedule contributes no active Forecast revenue. An existing recognized-revenue actual of USD 123 remains USD 123 on its original basis. |
| Parent deletion | Authorized deletion of its non-mirrored account/deal also leaves the same retained project and demand, original provenance and actual fact. Live parent FKs may be NULL, not recreated. A foreign tenant/environment or ordinary test identity sees none of that real demand. |
| Named continuity | Seven current managed people with matching capabilities, gross allocation 1 and same stable demand-key commitments satisfy those seven retained slots: matched 7, retained 7, incremental 0, gap 0. Repeat after SOW and then client deletion; all amounts remain the same without releasing those people to another account. |
| Extension and growth | Six explicitly retained people continue in an adjacent approved extension: 6 total, 6 retained, 0 incremental. If the next effective revision adds two slots: 8 total, 6 retained, 2 incremental; with only those six suitable people, matched 6 and gap 2. Pending extension does not alter today's approved interval. |
| Global competition | An overlapping tentative one-slot plan competes with a committed retained one-slot project for one suitable person: project matches 1, tentative plan matches 0/gap 1. Filtering to the tentative account does not free that person; Sales receives no hidden project/person identifiers. |
| Inclusive roll-off | A retained commitment ending 15 Nov occupies its slot through that day and releases on 16 Nov. Repeated deletion/event delivery does not advance the roll-off or allocate the same capacity twice. |
| Partial conversion without staffing coverage | Financial fraction 0.5 against a seven-person plan does not create 3.5 people. Report explicit unresolved staffing coverage; do not publish a complete summed 14 or arbitrarily discard one source. With reviewed coverage of 2 US slots and explicit residual 5 India, the combined total is exactly 7. |
| Missing/foreign baseline | Missing canonical staffing, conflicting source identity, missing tenant, changed baseline hash, foreign environment, forged fixture provenance or expired grant is rejected/quarantined or displayed as authorized incomplete state. None becomes complete zero demand, real-scope fallback, or an authorized test match. |
| CAS and replay | Two concurrent publications against one expected version produce exactly one accepted next version and one conflict; unchanged replay returns its original identity. Deletion/publication races produce a consistent retained source or fail safely, not partial lines or resurrected parents. |
| Sensitive evidence | People responses omit all pricing, rates, costs, financial snapshots and raw baseline payloads for every demand reader. Unauthorized Projects readers do not gain canonical financial fields merely because those fields were added for retention. |

## Handoff And Limits

No tests ran, and no fix or feature acceptance is established. The source tree
stayed at the stated baseline; lead-owned uncommitted corrections were not read
as part of this pinned audit. Exact HTTP naming and physical baseline storage
remain lead-owned design choices, not new policy invented by this report.

| Requirement | This audit's verification state | Remaining proof |
| --- | --- | --- |
| S21-01 / CO-09 | missing | Execute retained-demand preservation through SOW and parent cleanup, rollback/race/replay, without restoring financial schedules. |
| DG-06 / S21-16 | missing | Prove approved baseline and effective amendment propagation, without draft overwrite or duplicate project demand. |
| FC-05 | missing | Prove conversion lineage and exact staffing deduplication; monetary scope does not imply staffing allocation. |
| FC-07 / T22 / T23 | missing | Execute the oracle matrix and connected People/sourcing journey; adapter-only proof does not establish all sourcing/events/rules or staging behavior. |

These scoped states do not replace the lead's full acceptance scoreboard.
