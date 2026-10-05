# DealGate S21 and Forecast Implementation

Source: [original DOCX](references/DealGate_S21_and_Forecast_Implementation.docx).
Interaction reference: [approved Forecast preview](<references/DealGate_Forecast_Preview (1).html>).
Historical source: [S20 handoff](references/DealGate_S20_Closeout_Handoff.md).
Reconciliation and implementation decisions: [contracts](../s21/contracts.md).

The complete source text below is mechanically extracted from contract version 3.
Original wording, including historical claims and table-cell order, is preserved.
The source headings use spaces in IDs; the crosswalk normalizes them to hyphens.

## Contract Text
Complete product requirements and Codex execution instructions
Prepared for SmarTek21 engineering and the Codex integration lead 1 October 2026  |  Implementation contract version 3
Implementation mandate
Implement the complete S21 repair scope and the agreed Forecast feature as one integrated release. Deliver working deal tracking, SOW intake and governance, financial forecasting, account and company reporting, and resource planning. Use a new worktree and coordinated agents. Finish the connected workflows and their meaningful tests before requesting the product owner’s staging click-through.
This document replaces the execution instructions in the original S21 directive and consolidates its sixteen numbered findings, the multi-model SOW amendments, the earlier deal-path requirements and the accepted Forecast preview. Keep requirement IDs in commits, tests and the completion report. Existing controls remain in force unless a specific change below replaces them.
Required handoff files
This DOCX is the complete implementation contract. Extract it into docs/directives/s21-forecast-implementation.md, preserving all requirements, before changing application code.
DealGate_Forecast_Preview.html is the approved interaction and layout reference. Preserve Company & accounts, Overview, Revenue projection, Resource demand and Next opportunities. Its sample data, browser storage and simplified calculations are demonstration code, not the production implementation.
Read the repository’s AGENTS.md, CLAUDE.md, scoreboard.md, decisions.md, S15 CTA policy, S17 agreement rules, S19 deal path and S20 integration/checkpoint documents. Locate these by content if paths differ. Reconcile conflicting instructions explicitly; do not assume old reports describe the current build.
Nonnegotiable completion conditions
No orphaned screens, placeholder integrations, silent zero costs, test-user approvals, duplicate revenue, invented source fields or fake success states. All changes must persist through refresh and worker restart. Forecast totals must reconcile from component to SOW, account and company. Staff demand must reach the People or recruitment planning view without authorizing a hire.
The release is staged on an isolated environment and reported with exact frontend, API, worker and migration revisions. Do not merge to main or deploy production until the product owner completes the click-through. Work checkpoints are resumable progress reports, not deadlines that justify dropping scope.
How to use this document
Start with the Codex instruction on the next page. This version incorporates the S20 closeout carryover, CO-01 through CO-10, and tests T38 through T45. It preserves all S21, deal-path, Forecast and operational requirements. The final carryover sections reconcile the release baseline, remaining proof and execution controls.

Codex start instruction
Paste this instruction into Codex with this document, the approved HTML preview and the S20 handoff.
Implement the attached DealGate S21 and Forecast Implementation contract end to end. You are the integration lead. Use multiple agents effectively in separate worktrees, with explicit ownership and one integrator. Do not modify my current checkout or work directly on integrate/s20 or main. Preserve all existing uncommitted work.
First reconcile CO-01 and CO-02. S20 is reported merged as main 321b365 with tag s20-release; verify the full SHA, tag and final-image evidence. Base a new feat/s21-forecast branch and sibling worktree on verified main containing that release, or a reviewed newer descendant. Do not restart from the old S19 snapshot or integrate/s20. Record unresolved S20 rows separately, plus runtime revisions and dirty worktrees. Missing deployment proof blocks the affected gate, not independent isolated work.
Before application code, commit this directive, requirement checklist, S20 crosswalk, contracts, ownership map and execution plan. Retain S21-01 through S21-18, DG-01 through DG-06, FC-01 through FC-12, OP-01 through OP-05 and CO-01 through CO-10. Namespace legacy S20 tests separately from this contract’s T01 through T45. Preserve the state-machine, authorization, margin and deployment rules; record explicit corrections. Never infer completed fixes from a merge.
First verify the reported leak containment; reproduce and repair any remaining approval contamination in isolation. Do not confuse the deleted Liberty test client with the real SOW. Set concurrency from actual shared-account capacity before launching workers. Each worker owns a separate branch/worktree and assigned files; isolate database, storage, queues and mail. Only the lead integrates, orders migrations and deploys. Prove one connected deal-to-Forecast journey early, then expand coverage.
For each reproducible UI issue, write an exact-click regression test before fixing it. Do not manufacture a failure when the report does not reproduce. Add independent service and integration tests for financial arithmetic, dates, permissions, deletion, routing, retries and reconciliation. A visible number, 200 response, mocked success or test count is not proof. Exercise the real application API, database, worker and storage path; isolate only external systems where needed and separately verify their contracts.
Build all pricing models and Forecast views in this contract. Reuse the existing application components and calculation engine. Replace prototype data with persisted, permission-scoped services. Keep financial actuals separate from contract schedules; expose unavailable integrations honestly. Complete the Company X assessment-to-project example, account/company next-two-quarter reporting and HR resource visibility.
Continue through implementation, integration, migration rehearsal, meaningful tests and staging verification. Run targeted checks during development and the full required regression suite on the final combined revision. Budget limits trigger a durable checkpoint with the exact next command; they do not permit scope reduction. Ask only for a material unresolved business decision, unavailable access or a required infrastructure approval, after making the proposed action reviewable. Report every requirement with evidence. Stop before merge for my click-through.

Isolate the worktree and runtime
Select and record the baseline
Read-only discovery comes first: git status, worktree list, local and remote refs, recent history and the actual deployed revision. Fetch only as the repository permits. Determine which immutable commit includes the required prior work. Record the base SHA, branch provenance, dirty-tree summary, test baseline and dependency lockfile hashes in docs/s21/baseline.md. A new worktree shares Git objects and refs; it does not isolate databases or cloud resources. [R1]
Use the following command pattern after resolving the real base commit and available paths. Placeholders must be replaced; commands must never silently default to main.
git status --short
git worktree list --porcelain
git log --oneline --decorate -20
git worktree add -b feat/s21-forecast ../dealgate-s21-forecast <BASE_SHA>
# After the lead commits shared contracts, fork a lane from that commit
git worktree add -b s21/crm ../dealgate-s21-crm <CONTRACT_SHA>
Reuse an existing task worktree only after confirming its branch, base and owner. If names collide, use a unique task suffix. Never run reset --hard, clean -fd, force-push, remove another worktree or rewrite another agent’s branch to make setup convenient. Keep all original uncommitted files intact.
Separate runtime state as well as source files
Resource
Required isolation
Application processes
Dedicated ports, environment files and log paths per active lane. Do not change shared environment defaults.
Database and storage
Task-specific database/schema and object-store prefix; migration fixtures and destructive tests operate only here.
Workers and events
Separate queues, outbox consumers, webhook receiver paths, schedules and run IDs. A worker must not consume another environment’s work.
External systems
Read-only CRM parity checks when allowed; controlled test portal/records for mutations. Capture mail and signature requests in test sinks.
Credentials
Use approved secret injection. Never commit credentials, paste them into evidence, copy unrelated environment files or log document contents unnecessarily.

Publish and integrate through one owner
The lead owns the integration branch, migrations and staging deployment. Lanes submit small commits with tests and handoff notes. Integrate each commit once, update dependent branches intentionally, and rerun affected checks. Do not combine uncontrolled merges and duplicate cherry-picks. Keep a deployment lock so multiple agents cannot replace the shared preview simultaneously.

Agent ownership and execution order
These are logical roles, not five simultaneous workers. The lead first records shared-account limits, remaining capacity and lane dependencies. If capacity is unknown, start with one worker plus the lead; increase only with observed headroom. Schedule roles in waves, pause launches on throttling and checkpoint cleanly. Do not create sessions or accounts to evade limits.
Owner
Primary responsibility
Boundary
Lead
Architecture, shared contracts, migrations, integration, deploy, scoreboard and release gates
Sole owner of shared state-machine and schema changes; delegates implementations behind agreed interfaces.
A CRM and tracking
S21-09 to 14; owner/pipeline/BU mirror, query service, comments, actions, alerts and groups
Owns CRM adapter and tracking services; coordinates page changes with UI owner.
B SOW and governance
S21-01 to 08 and 16; workspace, deletion, routing, versions, approvals, signatures and handoff
Owns SOW lifecycle; shares model and financial contracts with C.
C Commercial engine
S21-15, 17 and 18; pricing registry, extraction schema, calendars, cost and revenue schedules
Owns deterministic calculations and fixtures; no separate margin engine.
D Forecast and People
FC-01 to 12; forecast services, all preview views, account/company aggregation and HR visibility
Consumes C’s schedules and A’s canonical account/deal references.
E Independent QA
Reported-click reproduction, test oracles, contract/permission tests, integrated E2E and release evidence
Reviews expected outcomes independently; does not approve its own implementation fixes.

Map these logical boundaries to actual repository paths before spawning agents. Assign each shared frontend file, schema, generated client, migration and dependency lockfile one writer. A lane requests shared changes through the lead; it must not edit another owner’s files or silently create a competing service.
Dependency waves
Wave 0: reconcile S20 code and proof under CO-01/02; record unresolved dependencies before implementation. Define contracts, ownership, capacity and isolation; verify leak containment.
Wave 1: schedule independent CRM, SOW and commercial lanes within the capacity limit. Prove a thin Pipeline → Deal → SOW → approval → signature → delivery → Forecast journey before expanding.
Wave 2: extend the proven journey to all models, amendments, actuals, forecasts and HR. Carryover source-sync work and infrastructure prerequisites remain explicit dependencies.
Wave 3: migration rehearsal, real dependency verification, failure testing, complete regression suite, staging evidence and product owner click-through.
Efficient handoffs
Each lane receives only its requirements, relevant files and contracts. Return changed files, commit SHA, behavior, tests with results, API/schema changes, open risks and the next dependency. Avoid full-chat broadcasts, repeated repository scans and full-suite runs after cosmetic changes. Cache dependencies and reuse deterministic fixtures; never cache a stale test verdict across code changes.

Architecture and shared domain contracts
Use the existing stack and modules wherever they fit. Keep one canonical CRM read model, one SOW lifecycle and one versioned commercial calculation engine. Forecast is a projection over these domains; it must not create a parallel source of contract truth.
Domain
Source and contract
Account and deal
HubSpot owns account/deal identity, CRM ownership, stage, pipeline, amount/currency, close date and mapped Business Unit. Local assignees are separate.
Agreement status
Client-scoped NDA/MSA documents on file. Presence is a document check, not legal clearance or an inferred signature.
SOW package
Created on successful file upload; immutable submitted versions, model/components, term, scope, resources, review cycle, signature and handoff.
Commercial inputs
Typed pricing components, calendars, allocations, rate/cost basis and versioned policy inputs. No free-form executable AI formulas.
Forecast plan
Current contract schedule plus separately identified proposals, assumptions and scenarios. A plan references its source SOW/deal and version.
Financial actuals
Imported from the identified Finance system or validated Finance import. Billed, recognized and collected values remain distinct.
People supply and demand
Existing resource/HR records supply skills, location, dates and availability. Forecast creates planning demand and traceable sourcing drafts.
Tracking and automation
Comments, next actions, saved groups, alerts and a transactional outbox. Shared permissions, audit and retry semantics.

Required shared invariants
Carry tenant, environment and authorization scope through queries, events, caches and exports. Aggregate only records the viewer is allowed to see; company totals require company-wide entitlement.
Use stable internal keys for relationships and human names for display. Store external IDs as strings; pipeline stage identity includes its pipeline. Choose a primary reporting account for multi-company associations so the same deal is not rolled up twice.
A SOW’s signed version remains authoritative while an amendment is pending. Submitted approval decisions bind to a version and calculation snapshot. A commercial edit cannot retain an obsolete approval.
Deduplicate by economic scope and effective period. A signed SOW replacing an opportunity, a revised schedule replacing an earlier version, or an extension continuing a team must not be counted twice.
Currency, decimal precision, timezone, calendar, calculation version, source version and as-of time travel with results. Unknown values are unresolved, not zero.

S21 01 through 04 SOW repair requirements
S21 01 Permanent deletion at every stage
Replace Archive with Delete SOW for authorized users at draft, submitted, review, approved, signed and handoff stages. Show one confirmation naming the SOW, its owned data and any retained dependencies. Reuse the deletion service if present. Return a deletion job/result that the UI follows until cleanup completes; do not show success while the SOW is still active.
Delete the package, owned uploads and versions, extracted data, scope, staffing, GM runs, approvals, SOW-only actions/comments and renewal drafts. Cancel tasks, reminders, signature envelopes where supported, scheduled jobs and queued notifications. Remove its schedule from active forecasts and all count/read models. A retry or late webhook must not restore it. Keep a minimal deletion audit/tombstone without retaining the deleted document payload.
Preserve the parent deal/client, their NDA/MSA files, other SOWs and unrelated comments. Preserve projects with delivery activity, timesheets, invoices and financial actuals; detach the removed source and label it. Only provably empty generated project shells may be included in the deletion manifest. Linked independent opportunities survive with a source-deleted marker; SOW-owned unpromoted forecast drafts are removed. Record this boundary and the reversal of Archive in decisions.md.
S21 02 Staffing and GM inside the workspace
Render Staffing & GM within the common SOW shell, with the same header, tabs, selected version, context and one readiness sidebar. Deep links may select a tab; clicking it must not leave the shell. Browser Back returns to the prior view with filters intact. Use the existing CTA state machine rather than independent buttons on each tab.
S21 03 Revisit every intake step
Every draft step supports Back and clickable completed steps: upload/review, scope, staffing/commercials and confirmation. Persist changes before navigation and show save errors. After submission, Edit starts a new draft revision with a change summary and reason. Previous submissions remain immutable; resubmission starts a fresh approval cycle. A user can correct a skipped reviewer before submitting.
S21 04 Populate overview truthfully
Show deal owner from the HubSpot owner mirror and a separate editable SOW owner/local assignee. A missing CRM owner is never replaced by the uploader. The local owner may default to the uploader. Distinguish Not assigned, Not provided, Unavailable and Needs confirmation. Display dates consistently only after resolving the year, locale, term and inclusive end rule; “April 12th” does not establish a year.
Show confirmed delivery model, pricing components, term, next action and responsible person. Provide inline editors for local fields and unresolved extraction values. Remove internal ID labels. Preserve revision chips and source evidence. Do not suppress missing-information states simply to make the page look complete.

S21 05 through 08 Approvals and routing
S21 05 and 06 Resolve reviewers before submission
Confirm SOW and Approvals preview each required function, primary/acting reviewer, reason and eligibility before submission. Allow authorized overrides within the eligible group; prevent bypassing mandatory functions or the CEO gate. Internal approvers and signature recipients are separate.
Function
Default reviewer
Fallback or condition
Delivery
Shawnna DelHierro shawnnad@smartek21.com
Srikanth Parimi srikanthp@smartek21.com Only while Shawnna is explicitly OOO
Sales
Janice Krpan janicek@smartek21.com
Required review function
Legal
Seema Anil seema@smartek21.com
Required review function
Finance
Scott Pfeiffer scottpf@smartek21.com
Required review function
CEO exception
Al Lalji al@smartek21.com
Required when applicable GM policy is breached

Seed real identities idempotently in People & access, not hard-coded user IDs. Store dated OOO windows and timezone. A generic delegate cannot replace the required Delivery fallback. Block submission when no eligible reviewer exists. OOO changes require audited reassignment of in-flight tasks and must preserve completed decisions.
Add Sales throughout schema, readiness, tasks and notifications. Preserve existing HR review requirements until removal is explicitly authorized; the prior agent’s suggestion is not approval. Keep HR’s group and planning access.
S21 07 Exclude test identities and repair contamination
Enforce eligibility when assigning, executing tasks, recording decisions and sending notifications. E2E users are eligible only for trusted test-environment/run records, never a user-editable tag. Scan existing business assignments; report contaminated rows, cancel pending invalid tasks and reassign with audit history. Investigate any completed test-user decisions separately and invalidate/re-review affected versions under the approved remediation procedure. Do not erase evidence.
S21 08 Verify email delivery
Inspect the actual SES account, region, sandbox status, verified sender/domain and rejection logs. Sandbox allows verified addresses or domains; individual verification may be unnecessary when the relevant domain is verified. The roster includes six addresses with the fallback. Preserve infrastructure plan/apply approval rules; prepare the plan before requesting approval. [R2, R3]
Assignment success, queued email, provider acceptance and delivery are separate statuses. Use the real outbox with idempotency, retries, dead-letter visibility and safe test recipients. Do not send test approvals to business users. Continue unrelated work while access is pending. Complete OP-01 through OP-05 for operational rollout.

S21 09 through 12 Pipeline and source data
S21 09 One filtered population
Clients, Opportunities, stage chips, summaries, saved groups and exports derive from the same authorized query predicate before pagination. Clients shows only accounts with at least one matching deal when deal filters are active, sorted by matching count by default. An explicit Show clients with no match toggle restores the rest. Keep matching and total-open counts clearly labeled. Tab counts reflect the same predicate and snapshot.
Stage chips show matching count/value, filter in place and update the URL without routing elsewhere. With multiple pipelines, select one or group chips by pipeline. Use actual stage definitions and closed/won metadata, not label ordering. Switching views preserves filters. Zero matches stays zero; an older response cannot replace a newer result. Provide Last activity oldest first and an Untouched for 14 days filter, distinguishing missing activity from confirmed inactivity.
S21 10 Company and deal owners
Mirror HubSpot owners, including inactive records needed to explain historic ownership, and resolve company and deal owner IDs separately. A missing DealGate login does not mean a missing CRM owner. Show No account owner when the company owner is absent, and Unassigned deal owner only when the deal owner is absent. If metadata cannot be resolved, show Owner details unavailable. Report measured source counts after reconciliation.
S21 11 Visible filter chips
Support owner multi-select, stage multi-select, Business Unit multi-select, pipeline, open/won/lost status, attention, SOW state and date field plus range. Date fields are created, expected close and last activity; presets include last 7/30/90 days, this quarter and custom range. Show every selected value as a removable chip. Removing one value preserves the others. Clear all, saved views, URL, refresh and Back must agree.
Persist last-used filters per user. A valid shared URL takes precedence over personal defaults. Validate malformed filters and bound custom dates. Publish date-boundary and timezone semantics. Client search, sorting and 25/50/100 pagination run server-side with stable tie-breakers; aggregation must not depend on the visible page.
S21 12 Clear names and required facts
Display deal name, client, pipeline name, stage label, amount/currency, close date, owner, Business Unit, SOW state, attention and last activity. Keep pipeline name on deal detail even for one pipeline; the list may omit a redundant column. Discover the actual Business Unit property name/type/options from the portal’s property definitions and record the mapping. Never guess its internal name. [R4, R5]
Business Unit remains visible: Not configured in HubSpot when the property is absent, Not provided when a configured property is empty, and Unavailable with a reason for a mapping/sync error. Apply CO-08. Breadcrumbs and identity labels across headings, search and exports use names; legitimate amounts or customer references may contain many digits. Resolve stale metadata without displaying IDs as names.

S21 13 and 14 Tracking and groups
S21 13 Deal work stays on the deal page
The deal page provides add, edit and complete next action with owner and due date, plus add/edit permitted comments and pin/unpin. Show author, timestamp, edited state and source. Save through the API, reload correctly and update latest-comment and activity summaries. Enforce author/role permissions server-side; reject stale concurrent edits rather than silently overwriting them.
Keep internal DealGate comments separate from HubSpot notes. Mirror readable CRM notes as read-only with their source, author and timestamp; never write internal staffing or margin discussions back to HubSpot. Confirm actual API availability/scopes before implementing the adapter. If permission is missing, internal comments still work and the CRM-note dependency is reported. Sanitize rendered note content. [R6]
S21 14 Persistent and usable alerts
Provide per-deal watch and alert controls. Stage changes, close date within 14 days and overdue next action default off. Include expiry/renewal and resource-planning change alerts where applicable. A watch star alone does not subscribe to alerts. Show settings and relevant delivery activity with permissions; notification details must not expose restricted commercial data.
Use the existing notification outbox. Define event keys per subject/version/recipient/threshold window. Repeated delivery attempts cannot create duplicate alerts. Rescheduling a due date cancels the old reminder. Completing an action, unwatching, disabling a rule or deleting its subject suppresses obsolete reminders. Respect recipient timezone, channel preferences and digest settings.
DG 01 Saved groups and manual watchlists
Build both requested group types: a saved rule-based view that updates as data changes, and a manual watchlist of deals or clients. Store group owner, visibility, entity type and validated rule expression. Store membership separately from rules. Explain stage predicates per pipeline; do not compare stage labels alphabetically or use a global “stage greater than Proposal” across pipelines.
Expose groups on Pipeline and the Command center with matching counts. Use a selector or overflow menu when tabs become crowded. Group membership, sharing and counts respect record access. Saving a group does not grant access to its records or change ownership. Deleted/merged CRM records reconcile without orphan membership.
DG 02 Consistent client summaries
The client page shows client name, HubSpot link, account owner, NDA/MSA status and upload links, open deal count/value, last activity, named opportunities, agreement files and activity. Each opportunity includes stage, currency/value, close date, owner, BU, SOW state and next action. “Open 0” and a listed deal must reconcile: closed deals are labeled and excluded from open counts consistently.
DG 03 One navigation context
Pipeline → client → deal → Upload SOW → SOW workspace is a supported journey. Each route has a stable deep link and return path. Filtering, scroll/page state and source context survive navigation. A link cannot silently transform a CRM deal with no SOW into an approval workspace.

S21 15 Calendar based staffing and economics
A staff-augmentation contract defines a term and N people; users should not manually calculate aggregate hours. Each role or resource assignment stores quantity, start/end, allocation, workweek, hours per day or shift pattern, location, timezone, applicable calendar, bill-rate basis and cost basis. Default dates from the confirmed term and allow bounded assignment overrides.
Calculate distinct quantities
Calculate daily overlap of assignment and active contract dates. Apply headcount and allocation once. Sum scheduled work according to the working pattern and calendar; do not multiply a per-resource result twice.
Derive billable hours from the confirmed billing rules, including holidays, leave, caps or minimums where contractual. Derive paid/cost-bearing hours separately. A paid holiday may create cost without revenue.
Hourly revenue uses billable hours and effective rates. Monthly and fixed fees use their own pricing components; staffing calendars estimate their cost and capacity. Manual hour estimates remain an explicit supported input where appropriate, not a universal mandatory field.
Use loaded cost rates or salary allocation from the approved cost model. Never convert missing HR costs to zero or present GM as passed when costing is incomplete. Identify manual overrides, reason, author and effective period.
Calendar data and transparency
Calendars are versioned configuration by country/region/company/client and may differ within onshore or offshore teams. Seed relevant calendars but require coverage for every contract year, not only 2026/2027. Include observed holidays, weekend rules and service-specific exceptions. MSP coverage may require holiday or weekend staffing. Never substitute an unconfirmed 160-hour month.
Show a monthly roster breakdown of people, workdays, exclusions, allocation, scheduled/billable/paid hours, revenue, cost and GM, with a “How calculated” view. Preserve the calendar, rate, FX and calculation versions used at submission. Date-only terms use the confirmed local business calendar; avoid timezone shifts that move a contract boundary by one day.
Margin policy and approval
Reuse the existing GM engine. The required business floors are 35% for US work and 50% for India/offshore work. Enforce the configured effective policy at the relevant location/component and package level; a blended average must not hide a component breach. A below-floor result requires Al’s exception decision and explanation. If the repository policy conflicts with these requirements, record the conflict and resolve it before approving affected work.
Package GM is based on total revenue and total cost, not the arithmetic mean of row percentages. Zero or unresolved revenue produces Not assessed, not a divide-by-zero value or an automatic pass. Preserve policy version and any explicit exception. A forecast planning margin is never an approval decision.

S21 16 through 18 Amendments and SOW models
S21 16 Extensions and nonrenewal
On signed or released SOWs, Extend creates an amendment draft with the original version link, new effective period and changed dates, rates, quantities, scope, fees, service obligations or calendars. Show original, proposed and active terms separately. Recalculate changed/added periods and display the financial and staffing delta. Detect overlap and gaps explicitly; never count the full original contract again as extension revenue.
The amendment repeats applicable reviews, CEO exception and required signature. The current signed version stays in force until the amendment satisfies its effective conditions. Future changes activate on their effective date. A backdated amendment uses an explicit correction process; it cannot silently overwrite closed-period actuals. Update Projects, resource roll-offs, alerts and forecasts through the same published event.
Keep the two-calendar-month renewal reminder rule unless the authoritative policy says otherwise. Provide Undecided, Renew/Extend and Not renewing. Nonrenewal leaves current delivery active through the end date and creates closeout/roll-off actions. An extension at unchanged rates can still change GM because workdays, paid holidays, mix and fixed costs change.
S21 17 Separate delivery from pricing
Represent a SOW package with one or more delivery workstreams and commercial components. Delivery may be staff augmentation, managed service, project, consulting or assessment. Pricing may be hourly/daily, recurring, fixed assignment/total fixed fee, milestone, unit/story point or a supported combination. Term, billing cadence and cost model are distinct dimensions.
Use a versioned model registry for required fields, validation, editors and deterministic calculation modules. New names or parameter combinations may be configuration; genuinely new calculation logic requires a tested module. Do not execute formulas produced by the model. Unknown or unsupported terms remain a preserved draft with Needs confirmation or Unsupported model, never a forced staff-augmentation classification.
S21 18 Model coverage and migration
Support the profiles on the next page through upload, extraction, correction, confirmation, scope, financials, review, signature, handoff, amendment and forecast. Include scanned tables and hybrid documents. Preserve source evidence and override history. Changing a model shows incompatible inputs and a change summary before replacing them; signed history is immutable.
Migrate known legacy model values deterministically. Leave unresolved drafts flagged for review; do not silently reclassify signed SOWs or recalculate their historical approval basis. Report migration counts, unknown models, missing costs and unresolved dates. Fixtures must cover each profile plus ambiguous and unsupported documents.

Commercial model behavior
Every supported profile uses the same versioned SOW lifecycle. The UI asks only for relevant fields. Pricing labels alone do not define revenue timing or delivery cost. Billing schedules, service forecasts and recognized actual revenue remain distinct.
Profile
Required commercial behavior
Cost and resource behavior
Fixed cost assignment or fixed fee period
Store one total fee, scope and term. Allocate to confirmed service periods or milestones. A total fee does not repeat monthly. Support installment billing separately.
Use resource calendar estimates, fixed/direct costs and shared-cost allocation. Billable hours need not be supplied to establish fee revenue.
MSP or managed service
Recurring fee, service period, included scope/units, overages, proration, credits and billing cadence. Model setup fees as separate components.
Coverage and roster may include nights, weekends or holidays. Account for continuing teams and agreed SLA/coverage costs.
Staff augmentation
Headcount, allocation, resource dates, calendars and hourly/daily/monthly rates. Calculate quantities automatically.
Separate scheduled, paid and billable hours; calculate by role/location and effective cost rate.
Project or milestone
Deliverables, acceptance conditions, milestone values and dates. Distinguish planned milestone completion from approved invoicing and recognized revenue.
Staffing plan and nonlabor cost track the delivery period, not just payment dates.
Time and materials
Rate, unit, estimate, cap/minimum and approved usage. Support calendar-derived estimates and explicit manual quantities.
Forecast uses the estimate; actual quantities come from the identified time/usage source and remain separately labeled.
Story point or unit
Confirm whether points/units are billable accepted quantities, delivery estimates, sprint fees or capacity fees. Price only the contractual basis.
Never apply a universal story-point-to-hours conversion. Estimate delivery cost independently.
Hybrid
Version and calculate each component on its own effective dates, unit and currency; roll up without duplicate fees.
Allocate shared resource/direct costs once. Retain component/location GM checks.

Incomplete and conflicting terms
A missing year, conflicting fee, ambiguous currency, unsupported formula or insufficient staffing detail creates a targeted exception. Show the source clause and the field needing a decision. Draft estimates may be explored with visible assumptions; submission cannot treat a material unresolved value as approved. Do not discard the uploaded document when extraction fails.
Extensibility boundary
The system should detect many SOW structures, but must not claim that arbitrary new commercial logic is already supported. Store unfamiliar terms and evidence, allow a controlled manual model, and implement a new calculation module when necessary. Keep the same lifecycle and reporting interfaces so adding a model does not require rebuilding every screen.

Complete the deal to delivery path
DG 04 A deal is not a SOW
Use a dedicated deal route such as /deals/{id}, following existing route conventions. Show HubSpot facts and link, current sales stage within the correct pipeline, client NDA/MSA status, editable next action, comments, alerts and linked plans. Without a SOW, show Upload SOW. Do not show Delete SOW, SOW readiness or an internal approval stepper when no document exists.
Upload opens the studio pre-linked to the deal and client. Successful file storage creates the draft package; an interrupted upload must be retryable without duplicates or orphaned objects. If SOWs exist, show each with its own gate and version. Never suggest that every deal has one shared approval state. Keep the sales stage strip and internal gate strip distinct.
Remove automatic creation of empty SOW/workspace records during CRM sync. Inventory existing stubs, classify them by actual attachments/dependencies and produce a dry-run cleanup report. Remove only verified empty stubs through a controlled idempotent migration; ambiguous records stay flagged for review. Report before/after counts. An application fix alone is not evidence that existing data is clean.
DG 05 Client agreements
Show NDA and MSA checkmarks at client level with upload/view links beside each. A check means a document is on file under the S17 rule, nothing more. The same status appears on the client, deal and SOW workspace. Replacing a file updates the version and audit record. Deleting a SOW cannot delete these client-owned agreements. Do not turn document presence into an invented legal approval gate.
DG 06 One continuous SOW workspace
Keep Overview, Scope, Staffing & GM, Approvals, Documents, Signature, Handoff and Activity inside the workspace. Show deal/client names, owner names, current version, status and one readiness sidebar. The internal progression is Intake → Scope & GM → Reviews → CEO when required → Signature → Handoff. Show why a step is blocked, who owns it and the next permitted action. Reuse S15’s CTA state machine.
Every permitted draft section remains editable. After submission, material edits create a new version, invalidate affected approvals and require resubmission. Approvals bind to a document and financial snapshot. Signature requests reference the approved immutable package, and callbacks validate identity, version and current state. Handoff occurs once only after required approval/signature conditions; repeated callbacks cannot create duplicate projects.
Delivery and planning stay connected
Handoff carries term, scope, resources, costs, model-specific milestones or service obligations and source links. Projects receives the active signed term and subsequent effective amendments. Resource roll-offs and forecast schedules update from the same event. Forecast suggestions and unsigned proposals must not change an active delivery commitment.
The Command center, Pipeline, My work, SOW picker, Signed handoff and Forecast use the same relevant read services. A deleted package disappears consistently; a changed client/deal name propagates; a query error produces an error state rather than a plausible stale or empty summary.

Forecast screens and consolidated reporting
FC 01 Preserve the accepted experience
Implement Forecast in the existing DealGate shell using the approved HTML as the interaction reference. Retain five views: Company & accounts as default, Overview, Revenue projection, Resource demand and Next opportunities. Provide clear selected filters, remove-one chips, saved views, source drilldowns, edit assumptions, automation controls and exports. Use persisted API data, not localStorage as the system of record.
FC 02 Company outlook
Show current month, current quarter and the next two full quarters by default. Allow one, two or four future quarters and month-level drilldown. Use calendar quarters initially, make fiscal-calendar configuration explicit, and derive periods from the live as-of date in the organization timezone. On 1 October 2026 the current quarter is Q4 2026 and the next two are Q1 and Q2 2027; the combined future total excludes Q4.
Present signed schedules and potential revenue separately in the chart and cards. Switch between Committed, Expected and Upside. Show future signed coverage, estimated delivery cost, planning GM, renewal/extension dependency, revenue ending without replacement and account concentration. Label every measure’s period, currency, scenario and source basis. A role-limited or filtered view must say Selected total or My portfolio, not Company total.
FC 03 Account outlook
One row per account compares current month, current quarter, each selected future quarter, combined future total and signed coverage. Drill into the account to see SOWs, pricing components, linked growth opportunities, assumptions, staffing and source evidence. The sum of account rows equals the same scoped company total before display rounding. Include accounts with no future plan when they have current work or are explicitly requested.
Account drilldown preserves the chosen periods, filters and scenario. Editing a permitted source projection updates the account, company and resource views together after persistence. Opening monthly detail for current quarter plus four future quarters must preserve all fifteen months rather than reverting to a shorter default.
FC 04 SOW and monthly revenue views
Every SOW has its current schedule, end date and next-step state. Show follow-on project, renewal, extension, upsell, cross-sell, no opportunity identified, undecided or nonrenewal as appropriate. A valid no-opportunity state is better than an invented sale. Display monthly revenue/cost, model, status, probability and full-term versus selected-horizon values distinctly.
Revenue projection supports account, owner, BU, pipeline/stage, model, forecast status and period filters where applicable. Show signed, tentative, won-but-unsigned, excluded and unresolved items explicitly. A user can trace any total back to its source rows, calculation version and assumptions. Overview highlights decisions, expiry risk and the assessment-to-project journey without duplicating another dashboard’s logic.

Forecast financial calculation contract
FC 05 Scenarios and economic scope
Generate time-bucketed schedules from confirmed commercial components. Committed is the active signed schedule in the selected period. Expected adds each eligible unsigned plan’s in-period revenue multiplied once by its explicit win probability. Upside adds its full eligible value. Apply identical eligibility and timing to cost scenarios, while retaining separately identified unavoidable costs. Extraction confidence is never win probability.
A numeric planning draft may contribute provisionally when its dates, pricing, probability and assumptions are explicit; label Needs review and expose the provisional subtotal/filter. Incomplete or conflicting commercial inputs stay visible but are excluded from numeric totals with an explanation. Closed-lost, dismissed and expired plans do not contribute. Won-but-unsigned remains distinguishable from signed work. Missing probability is unresolved, not an automatic 0% or 100%.
Link each proposal to a canonical economic scope. On conversion, the matching signed schedule replaces that proposal exactly once. Partial conversion retires only the contracted portion and retains a documented residual. Multiple SOWs under a deal must not each inherit the full deal amount. A HubSpot deal amount is a source fact, not automatically a new revenue line. Mutually exclusive options belong to one scenario group, not an additive bundle.
Timing currency and margin
Use Decimal or minor currency units with explicit rounding. Schedule allocation must conserve the component total to the currency’s smallest unit, including final-bucket residuals. Store original currency and a versioned reporting FX rate/date; never sum unlike currencies without conversion. Unknown currency or missing FX remains unresolved. Recompute after date, rate, model or scope changes while preserving prior snapshots.
Signed coverage uses signed revenue divided by Expected revenue in the same future period, with N/A when the denominator is zero. Portfolio GM uses total revenue less total cost divided by total revenue; it is not the average of row margins. Display missing cost coverage and do not publish a misleading complete GM. Account concentration identifies its scenario, horizon and denominator. Expected revenue is an assumption-based forecast, not guaranteed revenue.
FC 06 Actuals and the current period
Keep contract value, service-month forecast, invoice/billed amounts, recognized revenue and cash collected as separate measures. Use the actual Finance connector already available; if none exists, deliver a permissioned validated import with source IDs, accounting period, currency, corrections and import history. Do not invent a finance vendor or claim a live connection from a stub adapter.
A current-period estimate may combine recognized actuals through a stated cutoff with remaining service forecast only when their basis and coverage align. Replace covered time/scope rather than adding actuals on top of the whole period forecast. If only invoice data exists, show billed actuals separately; do not call them recognized revenue. With no actuals, show Signed schedule and Actuals unavailable, preserving the behavior of the agreed preview.

Forecast resource demand and pipeline linkage
FC 07 Give HR useful lead time
For every potential engagement, store role, skills, level, quantity, location/timezone, start/end, allocation, delivery model, source plan and owner. Show month-by-month concurrent demand, full headcount, FTE/allocation and required skills. A seven-person opportunity at 70% win probability still needs seven people; do not turn it into 4.9 people for recruiting.
Keep tentative, committed, reserved and hired states distinct. Read skills, availability, bench and roll-off dates from the existing People system; if unavailable, provide a managed import and mark freshness. Match by capability, location, level, dates and allocation. Allocate available capacity once per overlapping period across the entire scoped portfolio, not afresh on each account screen. A tentative match is not a reservation.
Show gaps and sourcing-by dates using configurable lead times by skill/location. The preview’s 45-day onshore and 30-day offshore lead times are starter defaults, not universal facts. Include current committed assignments, continuing renewal/extension teams and release dates. An unchanged six-person extension is a retention/continuity requirement, not six automatic new hires. Model incremental headcount separately.
Expose planning demand in People/recruitment with account, likely start, skills, quantities, probability, status and source link. Prepare a sourcing-plan draft with an idempotent link to the forecast version. Changes to timing, probability, scope, staffing or nonrenewal update that draft and its change history. Alerts respect user preferences and sensitive financial-field permissions.
FC 08 Connect growth to the pipeline
A growth plan has a canonical account and optional source SOW plus a linked CRM deal or an explicit Local forecast only state. Existing HubSpot deals are linked by authoritative identity and reviewed matching; never create duplicates based on similar names. Display local plans in a clearly labeled Forecast opportunities view or filter so Sales and Delivery can track them before a CRM deal exists.
Keep the existing HubSpot deal mirror read-only unless write access and the create/update workflow are explicitly configured. Promotion can link a deal created in HubSpot or use an approved connector operation. Do not silently write AI suggestions into HubSpot. If write scope is unavailable, linking/import reconciliation remains fully usable and the missing write capability is reported.
Company X acceptance journey
A four-week assessment produces findings supporting a potential six-month project starting the next month. Propose the financial plan and seven roles: two onshore and five offshore, with skills and dates. Show source evidence and assumptions, publish planning demand to HR, link the pipeline opportunity, then replace forecast revenue with the signed SOW upon conversion. A start-date slip updates both revenue quarters and sourcing dates. No quote, staffing reservation, client communication or hire is authorized by a forecast alone.

AI extraction and bounded automation
FC 09 Extract evidence and prepare plans
Process uploaded SOWs and amendments, including supported scans and tables, through the existing extraction/OCR infrastructure. Extract delivery model, pricing components, term, fees/rates, currencies, units, staffing, milestones, coverage, renewal/notice clauses and obligations. Preserve page/section or table-cell evidence, document version/hash, extraction version and the distinction between extracted fact and inferred assumption.
Generate follow-on candidates from assessment findings, SOW scope, delivery progress, account signals and available CRM data. A SOW often describes current obligations, not the value or probability of future work. Proposed projects, fees, start dates and teams without contractual evidence must remain explicit planning assumptions. Do not invent unavailable skills, rates, customer commitments or approval policies.
Show evidence, uncertainty, missing fields and conflicts in a focused exceptions queue. Prefill supported values automatically. Allow targeted correction, reject/dismiss, defer and bulk acceptance of permitted noncritical fields. Confirm material commercial terms before SOW submission; do not require humans to retype all extracted data. Preserve manual overrides on re-extraction until a source change is reviewed.
FC 10 Automate repeatable work
Provide persisted, permissioned rules for extraction on upload, refresh on amendment/source change, renewal signals, growth suggestions, HR planning visibility, notifications and exception thresholds. Automatically compute schedules, update aggregates, prepare planning drafts and refresh sourcing needs once supported inputs exist. Expose job status, last success, next retry and stale-data warnings; a running animation is not proof of integration.
Do not automate irreversible business commitments: approving below-floor GM, signing, quoting, emailing clients, reserving named people or authorizing hires remain explicit authorized workflows. A rules switch cannot bypass server permissions or approval requirements. It must change worker behavior, not only its visual state.
Reliability and AI evaluation
Treat document text as untrusted data. Instructions embedded in a SOW cannot change approvers, thresholds, permissions or tool behavior. Parse into a strict schema and run deterministic validation/calculations. Use document hash plus extraction/prompt/schema version to deduplicate work; retries must not create duplicate SOWs or opportunities. Retain an override layer so a new extraction cannot erase a confirmed correction.
Test against a versioned, held-out document corpus containing every supported pricing profile, conflicting dates/fees, scanned tables, unsupported terms and malicious instructions. Measure critical-field correctness and evidence fidelity separately from aggregate model scores. All known critical errors in the acceptance corpus must route to review or be corrected before submission. Run a small controlled live-model evaluation in staging; deterministic provider fixtures cover routine CI and fault paths.
Use calibrated confidence only where measured. Do not present an arbitrary model score as a guaranteed accuracy percentage. Keep win probability, extraction confidence, data completeness and business readiness as separate fields throughout the UI and API.

Data APIs events and permissions
Adapt these logical contracts to the existing schema and routes; do not introduce duplicate services because a name differs. Publish typed request/response contracts and migration ownership before dependent lanes implement clients. Existing hubspot_pipeline remains the shared CRM read path if it is the current service.
Contract
Required persisted fields and behavior
CRM read model
Portal/account/deal keys; primary reporting account; owners; pipeline/stage labels and metadata; mapped BU; source timestamps; sync status; currency; query/filter version.
SOW and commercial version
Package/version/document hash; confirmed model/components; dates; scope; calendars; resource assignments; rates/costs; evidence/overrides; policy/calculation version; approval cycle.
Forecast plan and schedule
Plan/version; economic scope; source IDs; lifecycle; probability and provenance; effective dates; revenue/cost buckets; currency/FX; scenario group; replacement/conversion link; assumptions.
People demand and actuals
Demand/version/role/date/allocation; availability source; tentative match and sourcing plan. Finance actual source ID, measure type, period, currency and correction version.
Tracking and jobs
Comment/action/group ownership; rules and memberships; watcher preferences; job/outbox identity; retry state; audit correlation; deleted-subject tombstone.

API semantics
Provide paginated list/search, aggregates and exports using a shared filter object. Resource APIs cover SOW versions, reviewer preview, submission, amendments, deletion preview/status, forecast plans/schedules, company/account summaries, evidence, demand and rules. Return named labels plus keys, permission capabilities, missing-data reasons, source freshness and the calculation basis. Use schema validation and optimistic version checks on writes; repeated submit/upload/delete requests use idempotency keys.
FC 11 Reporting and exports
Export the same authorized population and scenario as the screen, across all pages. Include period bounds, timezone, currency/FX basis, as-of time, actual/forecast classification and calculation version. Store a dated forecast snapshot for later comparison; current estimates may change without rewriting history. Protect CSV exports against spreadsheet formula injection and hide restricted rates/costs from recruitment roles.
FC 12 Recompute and propagate consistently
Publish changes transactionally with source updates. Workers recompute affected schedules and invalidate account/company/People caches by tenant and permission scope. Use deterministic event IDs, idempotent consumers, bounded retries and dead-letter recovery. Reject obsolete versions and tolerate duplicate/out-of-order events. Reads expose their source watermark; no screen may report a fresh total from mixed incompatible snapshots.
Authorize server-side reads, edits, deletion, reviewer overrides, exports and administrative rules. Sales sees permitted commercial data; HR/recruitment sees demand and appropriate source context; individual compensation or GM requires explicit access. Test record-level and field-level isolation, including shared links, direct API calls and aggregate endpoints.

Integration migration and operational completion
CRM sync and metadata
Use the existing HubSpot authentication method and supported API versions, keeping credentials server-side. Confirm needed read scopes against the actual endpoints; do not repeat the unverified “notes/engagements read” scope label as a technical requirement. Paginate all owner, company and deal reads and preserve relevant associations. Read pipeline definitions and configured custom properties. Store a source-to-display mapping report. [R4–R6]
Verify webhook signatures, enqueue quickly and reconcile by source timestamps. Handle rate limits, retries, deletions, merged accounts and stale metadata. Retain nightly reconciliation and incremental note polling if compatible with the actual API; make the cadence configurable. A fifteen-minute notes target is a starting configuration, not an assertion about universal webhook limitations. Catch up after outages without duplicate activity.
Finance HR signature and email dependencies
Inventory every actual connector, endpoint, permission and test environment. Reuse existing adapters. For Finance/HR without a connector, implement a validated import with deduplication, error reporting and provenance; identify this as an import, not a live integration. Signature must use the repository’s configured provider/sandbox and preserve document/version binding. No synthetic success may close an integration gate.
Keep environment-scoped mail capture, trusted test identities and safe provider test modes. Business approval routing and test routing must remain separate even when using the same application build. Infra changes follow the repository plan/apply process; prepare concrete plans, report dependencies and keep unrelated implementation moving.
Migration and cleanup
Create additive, reversible migrations first; backfill owners, pipeline/stage labels, BU, model mappings and forecast references in resumable batches. Report counts and field coverage against source data. Preserve custom overrides.
Rehearse on a representative isolated copy. Test restart after a partial batch, duplicate execution, malformed rows and active concurrent writes. Deploy compatible application/worker versions in the documented order.
Inventory and repair test-user assignments and empty stubs separately from schema changes. Produce a reviewed deletion manifest. Never remove records merely because a name looks synthetic or a field is blank.
Rebuild projections after backfill, compare source totals to SOW/account/company results and verify all count surfaces. Keep a pre-migration backup and a tested restore/rollback procedure for the isolated rehearsal.
Operability and performance
Instrument CRM lag, extraction failures, review eligibility errors, outbox age, deleted-subject retries, forecast calculation failures and unreconciled totals. Use correlation IDs without leaking sensitive payloads. Index measured filter/association access paths. For an initial load target, test at least 10,000 deals, 1,000 SOWs and 24 monthly buckets, or the measured production volume if larger; report concurrency and hardware. Target p95 under two seconds for lists and three seconds for account/company summaries under the stated test load, or document the remaining bottleneck as an unmet requirement.

Testing that proves business behavior
Treat the acceptance matrix as a set of risks to prove, not a request for one test per row. Tests may share fixtures but must assert independent outcomes. QA owns the oracle; implementation code must not calculate its own expected answer. Each reproducible defect starts with the reported UI clicks and a red result on the correct baseline.
Test layers and evidence
Layer
Required proof
Unit and calculation
Independently derived quantities, rates, costs, proration, dates, rounding, FX and scenario math. Boundary/property tests for conserved totals and nonduplication.
Service and database
Real database, migrations, constraints, authorization, concurrent writes, deletion cascades, idempotency and transaction/outbox behavior.
Worker and contract
Actual job consumption with retries, duplicates, stale events and failures. External API fixtures match documented contracts; separately test configured external services.
Browser journeys
Use real application API/database/worker paths. Assert visible names, membership, amounts, persistence and next-state behavior after user clicks and reloads.
Staging parity
Exact combined deployment revisions, role-aware journeys, safe test records, CRM field parity, integration results and source-to-summary reconciliation.

Tests that do not count as completion
Assertions such as true equals true, a static header exists, a button was clicked, or a response returned 200 without verifying its meaning.
Mocking the feature’s own API/financial service and asserting the mock’s canned output, deriving expected results from the same production calculator, or approving only screenshot snapshots.
Skipping failed tests, relaxing assertions to match a bug, hiding exceptions, substituting test users into real approval groups or retrying until a flaky test happens to pass.
Independent fixture corpus
Create synthetic documents and CRM records with different owners, pipelines, BUs, statuses and dates across at least three pages. Include every model, missing/inactive owners, ambiguous terms, mixed currencies, overlapping skill demand, all approval states and signed amendments. Fix clock, timezone and calendars. Use real names only for authorized source parity; use isolated identities for mutation journeys. Prove critical tests fail for a controlled wrong total, duplicated conversion or forbidden reviewer; remove the injected fault afterward.
Run efficiently
Run changed-module tests and one affected vertical journey during development. At integration checkpoints, run contract/migration tests and the affected cross-lane journeys. On the final combined revision, run all required existing gates and the complete new suite. Repeat only where a code change, failure or remaining risk warrants it. Archive full logs and traces; summarize results and failure causes in chat.

Acceptance tests for SOW repairs
Use these IDs in the test report. For each test, record fixture, role, precondition, action, independently expected result and observed result. Parameterize states or models when the business rule is shared.
Test and scope
Action and required observable result
T01 S21-01
Delete separate SOW fixtures at draft, submitted, review, approved, signed and handed-off states. Verify database/object cleanup, all count surfaces and a fresh upload. Preserve parent/client agreements, other SOWs and a project containing actuals. Inject late callbacks and retries; no resurrection or remaining active reminder.
T02 S21-02 and DG-06
From Overview click Staffing & GM, then Approvals and Back. Header, tabs, selected SOW/version and exactly one readiness panel stay visible. Deep-link and reload select the same tab.
T03 S21-03
Upload, edit scope, navigate forward/back and reload. Values persist. After submission, edit pricing; a new draft appears, old document/decisions remain immutable and resubmission invalidates stale approval authority.
T04 S21-04
Exercise empty CRM owner, unresolved owner metadata, missing year and ambiguous pricing. Show distinct honest states and local editors. Correct values and reload; no hidden hash or fabricated year/uploader-as-CRM-owner.
T05 S21-05
Skip reviewer selection in an earlier step, open Approvals, see planned functions and eligible names, edit a permitted reviewer and submit. Invalid or unauthorized reviewer IDs are rejected server-side.
T06 S21-06
Resolve Shawnna outside OOO, Srikanth inside the configured window and Shawnna after it. Check timezone boundaries, inactive fallback and in-flight reassignment. Normal GM omits conditional CEO review; breached GM requires Al; incomplete costing blocks assessment.
T07 S21-07
Try to route, execute, decide and notify a real SOW with a test identity. All are rejected. A forged run tag cannot bypass controls. Repair a contaminated pending task and retain its audit trail. Validate the separate handling of already-recorded invalid decisions.
T08 S21-08
Submit a valid safe-test SOW. Verify real outbox → worker → test mail/provider flow and proper recipient resolution. Inject rejection, timeout and retry; show delivery status, one intended notification and recoverable failures. Confirm SES account/region separately; include T33 to T37 for rollout readiness.

Deletion failure proof
Include an object-store failure after the deletion request and a concurrent worker holding an old task. The SOW must be unavailable to business actions, cleanup must remain visible/retryable, and the worker must honor the deletion fence. A hidden row with intact active jobs is not permanent deletion.

Acceptance tests for tracking and models
Test and scope
Action and required observable result
T09 S21-09 and 11
Seed disjoint owners/BUs/stages across three pages. Click chips and combine filters. Verify exact row membership, client matching count, summaries and all-page export. Remove one chip, reload, Back and saved view. Zero matches stays zero; delay an old response to prove it cannot overwrite the new selection.
T10 S21-10 and 12
Compare every displayed CRM field to an authorized source snapshot, including owner with no DealGate login, pipeline label and real BU mapping. Company and deal ownership flags remain independent. Required identity labels show names across breadcrumbs, details, tables, search and export; legitimate numeric amounts remain valid.
T11 S21-13
Add/edit/pin a comment and create/edit/complete an action from the deal page. Reload and inspect latest activity. Check another role, unauthorized edits and simultaneous updates. CRM notes remain read-only and separately attributed.
T12 S21-14 and DG-01
Configure a per-user alert; trigger its event through the application. Change due date, complete action, disable rule and replay delivery. Obsolete reminders cancel and no duplicates send. Saved-rule groups update; manual watchlists do not change unexpectedly or leak inaccessible records.
T13 S21-15
Use the independent ten-person calendar oracle and partial-month/part-time/mixed-location cases. Verify scheduled, billable and paid hours, monthly cost/revenue/GM and holiday details. Missing calendars/costs remain unresolved; no mandatory manual aggregate hours.
T14 S21-16
Create extension with rate/headcount/term changes. Pending amendment leaves original active. Complete required approvals/signature and verify effective schedule, Project term, renewal alerts and continuing team. Test nonrenewal, overlapping periods and a late callback.
T15 S21-17 and 18
For each pricing profile, upload a real fixture file through the UI, inspect evidence, correct extraction, save/reload, calculate, approve, sign in sandbox and hand off. Include fixed assignment, recurring MSP, staffing, T&M, milestone, unit/story point and hybrid.
T16 S21-17 and 18
Use scans, conflicting totals/dates, missing year, missing currency, unsupported pricing and embedded hostile instructions. Extraction preserves the upload, flags exceptions and never changes reviewers or policies. Re-extraction keeps manual corrections until reviewed.

Carryover deal path checks
T17 covers DG-02 through DG-06: Pipeline → client → named deal with no SOW → Upload SOW → confirmation → complete workspace → signature → handoff. Verify NDA/MSA presence semantics, no stub/delete/readiness before upload, one project after repeated handoff events, clear gates, correct names and consistent open-deal counts. Run the existing test-data leak gate and route inventory as part of this journey.

Acceptance tests for Forecast
Test and scope
Action and required observable result
T18 FC-01 to 04
Open all five Forecast views using persisted data. Filter and drill company → account → SOW/opportunity → monthly detail. Preserve scope/period/scenario and show current quarter separately from future totals. Verify names, empty/error states and all controls perform an action.
T19 FC-02 to 05
Load the independent Company X fixture and the accepted six-account preview fixture. Verify signed, Expected and Upside per month/quarter, account sums and company totals. Change date/value/probability and reload; all affected views reconcile.
T20 FC-05 and 08
Link a forecast to a CRM deal, convert it to one signed SOW, then repeat sync. Contract replaces potential once. Test partial conversion, two SOWs under one deal, lost deals, duplicates, alternative options and amendments without double counting.
T21 FC-05 and 06
Test zero/unknown revenue, incomplete cost, mixed currencies, fixed-fee allocation, milestones and rounding conservation. Import actuals twice, apply a correction and combine only matched actual-to-date with uncovered forecast. Billed amounts never become recognized revenue silently.
T22 FC-07
Show the full Company X team of 2 onshore and 5 offshore at 70% probability. Change the scenario; headcount remains seven. Two overlapping opportunities compete for one available person; no double match. Check part-time capacity, roll-off, continuing teams and sourcing dates.
T23 FC-07 and 08
Publish forecast demand to the actual People/recruitment view; prepare a sourcing draft, change start/headcount and see the update. Repeated events do not create duplicate requests. Restricted users cannot view costs or reserve/hire through a planning endpoint.
T24 FC-09 and 10
Run a fixture SOW/findings through extraction, plan preparation, exception review and auto-refresh. Disable a rule and prove the worker honors it. Re-upload/retry/re-extract without duplicate plans or lost overrides. Evaluate a held-out live-model sample separately.
T25 FC-11 and 12
Export all authorized rows and reconcile to the screen and API at the same snapshot. Test historical forecast snapshots, stale events, concurrent edits and tenant/role boundaries, including aggregates, deep links and CSV fields.

Browser and usability coverage
T26 checks keyboard navigation, form labels, focus return after dialogs, validation errors, browser Back, loading/error/retry states, long names, zero data and desktop/mobile layouts. Tables may scroll within their container; the page must not overflow. Verify the actual screen and navigation, including controls outside table cells.

Independent numerical test oracles
Oracle A Company X fixed assignment
Controlled fixture: as of 1 October 2026, one signed four-week assessment contributes USD 24,000 in October. A separate unsigned fixed assignment runs 1 November 2026 through 30 April 2027, total USD 420,000, with an explicitly confirmed even service-month allocation and 70% win probability. Estimated cost is USD 210,000 over the same six months. This allocation is a fixture assumption, not a rule for every fixed-fee SOW.
Period
Signed
Weighted opportunity
Expected
October 2026
24,000
0
24,000
Q4 2026
24,000
98,000
122,000
Q1 2027
0
147,000
147,000
Q2 2027
0
49,000
49,000
Next two full quarters
0
196,000
196,000
Whole proposed term
0
294,000
294,000

Potential revenue is USD 70,000 per month; Expected is USD 49,000 per month. Whole-term cost is USD 210,000; its weighted planning cost is USD 147,000. Planning GM is 50% on either consistent basis. The team remains seven people, two onshore and five offshore. Moving the start to December shifts the full schedule; it does not change total contract value.
Oracle B Ten person staff augmentation
Use a synthetic fixture calendar, not an assumed national calendar: inclusive 1 October 2026 through 31 July 2027; Monday–Friday; ten people; eight hours/day; 100% allocation. Exclude these workdays from billing while treating them as paid: 2026-10-12, 11-11, 11-26, 12-25; 2027-01-01, 01-18, 02-15, 05-31, 06-18, 07-05.
Monthly billable workdays from October to July are 21, 19, 22, 19, 19, 23, 22, 20, 21 and 21: 207 total. Billable hours are 16,560; paid hours are 17,360 across 217 weekdays. At USD 100 billed/hour and USD 60 cost/paid hour, revenue is USD 1,656,000; cost is USD 1,041,600; GM is approximately 37.10145%. Independently verify these constants; never derive expected values by calling the production calendar engine.
Oracle C Approved preview reconciliation
Keep the HTML’s six-account sample as a separate presentation parity fixture: October signed USD 208,500; Q4 Expected USD 700,700; Q1 Expected USD 449,400; Q2 Expected USD 217,000; next-two-quarter Expected USD 666,400. Signed future revenue is USD 174,000; Upside is USD 894,400. These are test constants only. Production dates, rates, calendars and finance data must not inherit demo assumptions.

Cross system failure and release gates
Required integrated failure tests
Test
Fault and proof
T27
CRM 429/timeout, expired access and duplicate/out-of-order webhooks: retry and reconcile without data loss, duplicate records or misleading freshness.
T28
Worker restart between commit and event handling, duplicate upload/submit/handoff, storage failure and stale callback: one business result, visible retry state and no resurrection.
T29
Migrate a representative database, interrupt backfill and resume. Verify foreign keys, row counts, legacy model coverage, no lost agreements/actuals and a tested rollback/restore.
T30
Run the complete Company X journey plus one staffing extension and one deletion on the combined staging revision. Prove every integration boundary, resource update and aggregate reconciliation.
T31
Measure list/filter/summary/export behavior at the declared representative load. Verify pagination correctness, no per-row external API calls, bounded query counts and documented latency.
T32
Attempt unauthorized direct API edits, cross-account/tenant reads, cost-field access, forged test tags and reviewer bypass. Check audit and refusal; no data leakage through counts or exports.

Release sequence
Gate 1: contracts, CO-01/02 baseline reconciliation, requirement crosswalk and reproduced failures are committed. Record S20 proof gaps and dependencies separately from new feature progress.
Gate 2: lane code, focused tests, independent oracles and migrations pass; integration lead reviews shared interfaces and combines the work. Unimplemented adapters cannot pass this gate as working integrations.
Gate 3: on the combined revision, run the full required existing suite, test-data leak checks, type/lint/build checks, new acceptance suite, migration rehearsal and external contract verification. Resolve material failures; report dependencies honestly.
Gate 4: deploy the ready combined build through the repository workflow, including D5 if applicable. Match UI/API/worker/schema revisions to the release manifest; run smoke, full journeys, OP-01 to 05 and CO-01 to 10 evidence checks. An elapsed budget is not a deployment gate.
Gate 5: product owner clicks Pipeline → client → deal → upload → correct model → scope/staffing → reviews → signature → handoff, then Forecast → account/company → resource plan → extension → delete a safe test SOW. Include the human HubSpot canary and operational checklist, then stop for approval before merging.
Rollback and approval boundaries
Separate schema activation, flags and worker deployment for safe rollback; never delete business data to roll back. Preserve required infrastructure, mutation and merge approvals. After the approved merge, verify the workflow’s new main image, stable service and smoke under D-S20-D5b. Record its full SHA and digest; a pre-merge image or pending poll is not post-merge proof.

Evidence reporting and resumable execution
Required repository deliverables
File or equivalent
Required content
docs/directives/s21-forecast-implementation.md
Complete implementation contract extracted from this DOCX, with links to the HTML reference and any approved changes.
docs/s21/baseline.md and contracts.md
Base SHA/provenance, runtime inventory, source mapping, architecture, schema/API/event contracts, ownership and dependencies.
scoreboard.md and docs/s21/acceptance.md
Rows for S21-01 to 18, DG-01 to 06, FC-01 to 12, OP-01 to 05 and CO-01 to 10; original S20 IDs, tests and evidence. Separate lane totals.
docs/s21/release-report.md
Changed behavior, deployment revisions, migration/cleanup counts, test runs, source parity, known gaps, rollback and click-through checklist.
docs/s21/handoff.md
Current branch/commit, completed items, in-progress work, exact next command, blockers, agent ownership and failing-test reproduction.

Status must describe evidence
Use the repository’s five reporting states if defined. If absent, use Not started, In progress, Blocked, Implemented pending verification and Verified on staging. Keep their definitions explicit. “Not listed” is a reporting defect. Every blocked item names the dependency, attempted resolution, owner and next action. A code commit, local pass or deployed screen alone is not Verified on staging.
For each requirement record: behavior implemented; test ID and fixture; baseline reproduction or reason it did not reproduce; command/run ID; expected and actual result; environment/role; immutable frontend/API/worker/schema revisions; trace/screenshot/log path; unresolved risk. Screenshots support functional evidence and cannot replace it.
Token and context discipline
Use targeted rg searches and bounded reads; avoid dumping entire files, large logs or every test trace into the conversation. Store detailed artifacts and cite their paths.
Reuse the current architecture and fixtures. Do not rewrite stable modules or duplicate business logic to avoid learning the existing code. Prioritize the narrowest change that completes the user journey.
Send compact progress updates on findings and decisions. Maintain one source of truth in contracts and the scoreboard; agents report deltas instead of restating the whole plan.
At a context or time limit, commit coherent work, preserve uncommitted work safely if needed, and update handoff.md. Record exact pending operations and test commands. Resume from that checkpoint; never declare completion to satisfy an output budget.
Final completion report
Lead with what the user can now do. Report the full requirement matrix, integrated test outcomes, staging link and revisions, source/migration counts and remaining dependencies. Include deletion, routing, pricing, Forecast, People, all operational requirements and the S20 carryover crosswalk with separate totals. State Ready for product owner click-through only when the release gates support it. No main merge before that review.

Decisions source references and completion boundary
Resolve from evidence before guessing
Decision or dependency
Required handling
HR in default approvals
Preserve the existing requirement. Ask only if changing/removing it is necessary; the prior agent’s suggestion was not authorization.
Current baseline and stack
Verify main’s S20 release 321b365 and tag under CO-01. Pin a full SHA containing it; inspect newer descendants. Preserve integrate/s20 and dirty worktrees.
BU pipeline and notes
Discover actual metadata and permissions. CO-08 handles an absent BU property without inventing data or silently dropping the integration.
Financial actuals and People supply
Use existing connectors where available; otherwise deliver validated managed imports. Confirm source/basis, data ownership and freshness before claiming live integration.
Calendars policy and FX
Use confirmed location/client calendars, effective GM rules and an identified FX source. Missing inputs block the affected financial approval, not unrelated development.
SES and signature access
Verify the real account/region/provider and test environment. Prepare infrastructure plans and safe verification evidence; do not infer status from an old screenshot.
Forecast reporting conventions
Default to calendar quarters, organization timezone and configured reporting currency. Show signed schedule when actuals are unavailable. Any fiscal or accounting-policy change is explicit.

Reference hierarchy
Explicit requirements in this contract and subsequent product-owner decisions govern the requested change. The original S21 directive supplies the numbered findings; the S21 Review and Amendments supplies the corrections; the accepted DealGate_Forecast_Preview.html supplies the intended screens/interactions. Repository instructions define actual commands and infrastructure gates. Where implementation evidence conflicts with an old report, verify the current revision and report the result.
Primary technical references
[R1] Git worktree documentation. https://git-scm.com/docs/git-worktree
[R2] Amazon SES production access and regional sandbox restrictions. https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html
[R3] Amazon SES identity verification. https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html
[R4] HubSpot pipeline metadata. https://developers.hubspot.com/docs/api-reference/legacy/crm/pipelines/guide
[R5] HubSpot property definitions. https://developers.hubspot.com/docs/api-reference/legacy/crm/properties/guide
[R6] HubSpot notes. https://developers.hubspot.com/docs/api-reference/legacy/crm/activities/notes/guide
References reviewed 1 October 2026. Resolve current endpoint versions and scopes against the configured application during implementation. Do not migrate API versions incidentally without assessing compatibility.
Operational rollout requirements
OP-01 through OP-05 and tests T33 through T37 remain required in version 3. Treat statements that infrastructure is ready, a Liberty approval round was cancelled or SES is in sandbox as claims to verify against the current environment. Preserve all earlier S21, deal-path and Forecast requirements. The lead owns operational integration; CRM, SOW and QA agents contribute within their established boundaries.
OP 01 Review and apply the infrastructure changes
Inventory the actual Terraform module, backend/state, workspace, AWS account, region, credentials and current resources. Use the repository wrapper, including scripts/tf-init.sh if applicable. Include CO-06’s consumer and drift-adoption prerequisites alongside monitoring and SES configuration; validate and produce a fresh plan from the correct commit. Show resource addresses, intended changes, side effects and the full add/change/destroy summary before requesting approval.
Do not promise or enforce “6 to add, 0 to change, 0 to destroy.” Existing state, domain verification, six possible recipient identities and the alarm design determine the real count. Explain unexpected drift, replacements or unrelated changes and prepare a corrected plan before applying. Keep state locking enabled and prevent concurrent infrastructure changes from other agents.
Where the repository requires human interactive confirmation, the human enters yes after reviewing the actual plan. The agent must not supply the answer, pipe it into the process, use -auto-approve or switch to a saved-plan apply to bypass that control. Saved-plan apply does not itself prompt for confirmation. Use it only when the approved repository workflow permits a separately recorded approval of that exact plan. [R7]
Record approval and apply results, then inspect deployed resources and run the intended behavior checks. If apply partially fails, inspect state and re-plan; do not assume automatic rollback or repeat unrelated changes. Report Planned, Awaiting approval, Applied and Verified as separate infrastructure milestones. [R7]
HubSpot monitoring must detect stalled work
Implement environment-scoped monitoring for successful-sync heartbeat age, pending-change/queue age, repeated failures and dead-letter backlog as supported by the architecture. A quiet CRM must not look unhealthy merely because no deal changed; a stopped worker must not appear healthy because an old success metric remains. Configure missing-data handling, thresholds, evaluation windows, alert destinations and runbook links.
Publish measured freshness in the application and correlate it with the sync watermark. Test a stopped worker and delayed event safely in isolation, confirm the alarm and notification route activate, restore processing and confirm recovery. An alarm resource without metric emission or a working notification destination is incomplete. The two-minute canary target in OP-04 is a measured acceptance criterion; choose monitoring thresholds explicitly rather than assuming they are identical.
[R7] HashiCorp Terraform apply documentation. https://developer.hashicorp.com/terraform/cli/commands/apply
SES recipient verification and onboarding
OP 02 Verify the required email path
Determine the actual SES sender, sending region, sandbox status and existing identity verification. Check domain coverage before creating individual identities. Sandbox recipients can be verified addresses or domains; verification is regional. Do not require six individual clicks when the appropriate verified domain already covers the intended recipients. [R2, R3]
Use the six-person roster already specified under S21-06: Shawnna DelHierro, Janice Krpan, Seema Anil, Scott Pfeiffer, Al Lalji and Delivery fallback Srikanth Parimi at their listed addresses. Srikanth is included for mail readiness even when Shawnna is not OOO. Email verification does not create a DealGate account, grant permissions or make a person eligible for a review function.
If individual verification is necessary, configure only missing identities through the approved infrastructure workflow. Explain that identity creation can send verification email; do not repeatedly recreate identities or resend invitations on every deploy. The recipient completes the verification. Track address, region, verification method, current status, last checked time and any action needed. Never report Terraform resource creation as Verified.
Prepare this message for an authorized person to send only to recipients who need an individual verification: “You may receive an Amazon Web Services verification email for DealGate. Please verify your address using that email so you can receive approval notifications.” Do not send Teams messages or other communications unless separately authorized.
After verification, prove the configured sender → outbox → worker → SES → intended inbox path using an explicitly authorized delivery check. Capture provider message ID and delivery evidence; distinguish provider acceptance from confirmed delivery. Check suppression, bounces and failed sends. Routine automated tests continue to use safe sinks or simulator addresses.
OP 05 Prepare SES production access early
Prepare the production-access request now rather than leaving it until broad onboarding. Use the actual sending region, transactional purpose, https://app.dealgateapp.com, expected volume, intended recipients and truthful bounce/complaint handling. Do not assert controls exist until implemented. The request can be submitted through the console or CLI under the approved account workflow; record the submission and outcome. AWS describes an initial response within 24 hours, not guaranteed approval in that time. [R2]
After approval, verify the account status, sender authentication, quotas/rate controls, outbox behavior and a controlled delivery check to a recipient not relying on sandbox verification. If pending or denied, record the next action and keep the pilot within verified-recipient and quota constraints. Verified-domain internal recipients may already be eligible, but sandbox limits still matter; do not base the rollout boundary solely on “more than five users.”
Keep the status in docs/backlog/prod-environment.md or its repository equivalent, plus the active OP-05 checklist. It is a tracked rollout dependency with an owner, not a backlog entry that can be marked complete without evidence.
Recover Liberty Mutual and prove live sync
OP 03 Restore the Liberty approval workflow
Locate the precise real Liberty Mutual account, deal, SOW package and submitted version. The reported deletion of a stale non-mirror S14b test client is separate evidence and does not prove this repair. Inspect approval history and confirm whether the Finance assignment to E2E Staging Bot existed, whether that round was cancelled and whether any decision, notification or downstream action occurred. Do not assume the agent’s earlier summary proves cancellation. Preserve the SOW file, financial inputs and audit trail.
If contaminated work is still pending, cancel or fence that review cycle through the tested remediation path and repair eligibility. If a test identity recorded a decision, follow S21-07’s invalidation/re-review procedure and assess affected downstream steps. Do not delete history or resubmit an already valid active review cycle. Block stale tasks and callbacks from completing the cancelled round.
Before resubmission, show the exact version, the planned real reviewers and any validation errors. Verify Shawnna or the required OOO fallback, Janice, Seema and Scott; add Al only when the applicable GM exception requires him. Preserve any existing HR policy pending its explicit resolution. A missing eligible person is a routing problem; an unverified address is an email-delivery problem. Do not substitute a test user to solve either.
Give the product owner a working Submit for approval action on the preserved SOW. One intentional resubmission creates one new cycle linked to the correct version and superseded cycle; retries do not duplicate it. Verify tasks, activity, correct submitter name, notifications and the updated status. If email remains unavailable, display that limitation and apply the configured submission policy; do not claim email was delivered or make infrastructure waiting block unrelated UI and routing tests.
OP 04 Human initiated HubSpot canary
Make this a release acceptance step, not an optional future demonstration. Agree on the authorized portal/environment and a clearly named canary deal/account that cannot be mistaken for ordinary business work. The person uses known owner, pipeline, stage, amount/currency and close date; include Business Unit when configured, otherwise verify CO-08’s absent-property state. Do not create a production CRM record automatically as part of routine tests.
Record the HubSpot save/commit timestamp as t0 and first correct visibility through the normal DealGate UI as t1, using synchronized UTC evidence. Pass when the correct record appears within 120 seconds without manual sync, reimport or direct database writes. Document ordinary page refresh/automatic refresh behavior. Verify fields and client association, counts, filter membership and source timestamps; confirm that sync did not create an empty SOW.
Then change a stage or date in HubSpot and prove normal propagation without duplication. Retain source and application evidence, webhook/worker correlation, environment and immutable build revisions. If the target is missed, record measured latency, diagnose the path and repeat after fixing it. Missing access or human participation is Blocked, not Verified. Clean up the canary only through the agreed CRM policy and prove the mirror reconciles its resulting state.
Operational acceptance and human handoff
Add OP-01 through OP-05 to the scoreboard and run these checks alongside the original acceptance suite. The integration lead prepares everything available in advance. A required human action or AWS decision pauses that operation only; agents continue independent implementation and tests.
Test and requirement
Required result and evidence
T33 OP-01
Fresh Terraform plan identifies the correct account/region/state and exact resource diff. Approval matches the applied changes. In an isolated test, a sync stall triggers the intended alarm and destination; processing recovery clears it. Prove heartbeat/missing-data behavior and no false incident from a quiet CRM.
T34 OP-02
Verify readiness for all six roster addresses by domain or individual identity in the sending region. Distinguish identity created, verified, reviewer eligible, queued, accepted and delivered. No duplicate verification sends on routine deploy; an authorized delivery check reaches the intended recipient.
T35 OP-03
Inspect and repair the precise contaminated Liberty cycle. Preserve the SOW/version and history, reject old tasks/callbacks, preview real reviewers and resubmit once. Verify one new cycle and correct tasks/notifications. Exercise destructive/failure paths on an isolated fixture before any live remediation.
T36 OP-04
A human saves a named canary in HubSpot. Normal sync makes its complete record visible in DealGate within 120 seconds. Verify update propagation, filtering/counts and no SOW stub. Record t0/t1, source fields, revisions and cleanup/reconciliation; no manual sync shortcut.
T37 OP-05
Prepare and submit the truthful SES production-access request through the approved workflow. Verify actual outcome, quotas, sender configuration, bounce/complaint handling and controlled delivery after approval. Pending/denied remains a reported dependency; no false green.

Assign the remaining human actions precisely
Infrastructure owner: review the fresh resource-level plan and provide the required approval. Enter the interactive answer only where the repository mandates it; no blanket approval of a remembered resource count.
Recipients: complete email verification only when individual verification is actually needed. The agent monitors status and prepares any follow-up; it does not claim the recipient has clicked.
Product owner or authorized business user: review the repaired Liberty routing and intentionally resubmit once; perform the HubSpot canary with QA recording evidence.
Authorized AWS operator: submit or approve the prepared production-access request as required by account controls. AWS decides the outcome; the agent tracks and verifies it.
Operational release evidence
Create docs/s21/operations.md with the resource plan/apply evidence, alarm test, regional email-readiness matrix, Liberty cycle/version findings, canary latency, SES request status and links to T33–T37. Link it from the release report. A staging click-through may proceed while external approval is pending if limitations are clear; broad onboarding is not ready until the chosen email operating mode and outstanding dependencies meet the rollout gate.
S20 release baseline and carryover
CO-01 through CO-10 are part of the S21 and Forecast release. Preserve the uploaded DealGate_S20_Closeout_Handoff.md as a source record and attach a reconciliation; do not rewrite its historical claims. The later S21-1d step 5 report supersedes its pre-merge snapshot. A completed merge does not close an unproven business behavior.
Owners: Lead takes CO-01/02/06/10; CRM lane A takes CO-03/04/07/08; SOW lane B takes CO-05/09. Commercial and Forecast lanes support actuals and aggregation. QA owns independent acceptance evidence across all ten; shared-file changes remain with their assigned writer.
CO 01 Verify the released baseline and deployed image
The latest report identifies main 321b365, tag s20-release and retained integrate/s20 at 33c38a0. It reports deletion of origin branches feat/s20-w4 and feat/s20-w7. At push time staging used image s20-27e2edec, API task-definition revision 70, with smoke green and zero test-tagged clients and e2e-approver leaks on active real SOWs. Main-image rollout was still pending. These statements replace the attachment’s older main 8b5100c, rev 67 and “not merged” snapshot, subject to repository and deployment evidence.
Resolve the full merge SHA and release tag; inspect the tree and release note. Pin the S21 base to that main release or a reviewed newer main descendant containing it. Do not rerun the squash merge, recreate/delete branches, move the tag or copy integrate/s20 merely because the old handoff instructs it. Inspect any post-release integration-branch delta before deciding whether it belongs in S21.
Retrieve the background poll’s completed evidence if available; its reported identifier bu3mb0xrw is not proof of success or a portable session handle. Otherwise inspect the deployment read-only. Record intended full main SHA, image digest, running tasks, service stability and matching UI/API/worker/schema manifest, then run the actual check-only smoke command. Do not hard-code revision 71 or assume success after 10–15 minutes. On timeout/failure, preserve logs and record the next action without relaunching a deploy blindly.
CO 02 Reconcile the tests and scoreboard before new work
Read docs/releases/s20.md and docs/reports/s20/{scoreboard,tests,decisions}.md, plus repository instructions. Produce docs/s21/s20-carryover.md with every S20-only row not verified, its original state/proof, current evidence, owner and linked CO/S21 requirement. Resolve the fate of legacy S20 T32/T34 and FINAL-T38 explicitly. Never treat this document’s T32/T34 as those legacy tests or merge S20 and S21 totals.
Verify A1–A4 outcomes from actual run artifacts. Legacy seedClientWithDeal/X-Test-User tests belong in the local harness only when their dependencies require it; classify by test project and validated environment, document dev-harness-only exclusions, and run that suite locally in CI. Do not skip by filename merely to obtain green. Staging tests must exercise staging authentication and real service paths.
Investigate the reported t09 names and t40 client-row full-suite failures with traces, test order and fixture ownership. An isolated pass is diagnostic, not closure. Fix root causes or report a linked unresolved failure; do not retry to green. Record expected/discovered/executed/pass/fail/skip/xfail/not-run counts and reasons. FINAL-T38 needs its actual security assertions and complete applicable-suite evidence, not an automatic flip based on a summary.
Run full pytest and the correctly scoped Playwright projects on the final code revision; run staging serial to reproduce the reported full-suite conditions. Every skip/xfail needs a reason and linked requirement. Unresolved required behavior stays incomplete.
S20 cards and delivery journey
CO 03 Watching remains visible and counts each deal once
Carry forward W6-7 and W6-8 under DG-01 and S21-09/14. The Watching card renders zero for an empty watchlist. With one authorized watched deal belonging to three groups, the card and /pipeline?watching=true each show exactly one. Test membership, not a parseable paginator. Unwatch returns both to zero. Respect viewer access and current filters; duplicate memberships never inflate counts. QA reuses T12 and adds the populated cross-surface assertions in T39.
CO 04 SOWs in progress opens the matching approval list
Carry forward W4-1 using the product decision in the handoff: count distinct SOW packages currently in review and link to the SOW approvals view filtered to the same in-review scope. Do not route this card to Pipeline attention=pending_approval. Several review functions on one package count once; several SOW packages under one deal count separately. Card and destination use identical authorization, filter and snapshot semantics; pagination cannot change the total.
Test a meaningful mixed fixture: one deal with two in-review SOW packages, multiple review functions per package, and unrelated draft/approved packages. Include restricted records and zero state. Assert the exact included package identities and count on both card and destination. Keep sales-stage chips filtering in place; their behavior differs from a card that intentionally opens approvals.
CO 05 Prove signature through delivery and actuals
Carry forward W7-1 through W7-5 under DG-06, FC-06 and tests T17/T21/T30. Replace the legacy tests/e2e/specs/s20/t44-full-journey.spec.ts skip skeleton with an executable scenario, retaining its provenance. This legacy t44 is distinct from contract T44. The journey requires no HubSpot write: use an authorized existing mirrored deal or an isolated run-tagged fixture through the supported application path.
Create synthetic source and signed SOW PDFs under tests/fixtures/sow/. Signatories, commercial terms and version reference must match the approved fixture. Exercise upload → confirmation → required reviews with isolated eligible approvers → signed upload → signature verification → release → delivery acceptance → one named project on Projects → one month of independently known actuals → forecast-versus-actual revenue, cost and GM. Use actual API/database/worker/storage services; a mocked signature success alone is insufficient.
Assert stage order and refusal to release unsigned, mismatched-version or mismatched-signatory documents. Repeated acceptance or callbacks create one project. Financial actuals use the identified import/source, match the right period/version, and reconcile to SOW, account and company without replacing billed values with recognized revenue. If real provider access is needed, track that contract check separately from the deterministic signed-upload journey.
Run against the combined staging revision with a run ID and environment-scoped fixtures; block test reviewers from all real packages. Clean up owned test data and prove the leak gate is zero afterward. W7 rows become verified only with attributable staging evidence; a unit pass, merged code or “deferred by design” label does not complete this requested flow.
S20 continuous sync and source completeness
CO 06 Converge infrastructure and prove the consumer
Carry forward W1-A2 and W1-ALARMS/W4-5 with OP-01 and OP-04. The handoff says webhook intake and nightly reconciliation are live but the continuous SQS consumer was not applied after the S2-D state-drift incident. Inspect the current deployment before changing it. Consumer resources are a separate prerequisite from alarms and email identities; the reported roughly 30 resources is historical, not a plan expectation.
The lead owns a drift-adoption change: verify remote backend, state lock, account/region and existing resources; use scripts/tf-init.sh and stop if its local-state guard fails. Produce a reviewed whole-root plan showing only intended, understood changes. Resolve imports/drift deliberately; no blind state deletion, forced unlock or targeted apply that hides root drift. Prepare consumer configuration, permissions, queues, dead-letter handling, retries and rollback through the existing modules.
Apply only through OP-01’s required human approval. Inspect the running consumer, queue age, successful consumption, retries and reconcile recovery. Prove measured freshness with T42 and the human T36 canary; resource creation is not a latency result. If access or approval remains pending, keep dependent freshness gates Blocked and the UI honest about its active sync mode. Continue independent isolated lanes; do not silently defer the requested consumer capability.
CO 07 Prove metadata updates and crash recovery
Carry forward W1-A3, W1-A4, legacy S20 T28 and W1-T33. Exercise stage rename and company/deal association changes through the source adapter, with exact labels, account membership and counts after sync. Retain a separately identified configured-provider parity check. Internal IDs remain relationship keys, never replacement labels. Repeated and out-of-order source events must not duplicate records or undo a newer state.
Run the formerly deferred backfill chaos exercise in isolation. Kill the worker after a persisted scan checkpoint and around the record/event commit boundary, restart it and prove scan generation/cursor resumption. Verify atomic dedupe/checkpoint behavior, complete source coverage, no loss/duplicates, and no false deletions from an incomplete generation. Test deletion/reassociation reconciliation and dead-letter recovery through supported paths. Remove relevant xfails only after real assertions pass; retain failure evidence if not. Extend existing T27–T29; do not build a second backfill system.
CO 08 Handle a genuinely absent Business Unit property
W1-D10 reports no Business Unit property in the portal. Verify that claim against current deal-property metadata and permissions; “no property” differs from unreadable metadata or empty values. If absent, show Not configured in HubSpot, explain/disable the unavailable BU filter, and prepare the required internal name/type/options request for the CRM owner. Do not create a property without authorization or infer BU from owner, pipeline or company.
Still deliver the configured-property adapter, settings and tests for positive, absent, empty and inaccessible cases. When an authorized property becomes available, map it, backfill and prove filtering plus account/company Forecast grouping. Default forecasts remain usable without BU and expose unclassified data explicitly. If the property stays absent, report the external dependency; do not mark live BU parity verified. T36 can verify the absence honestly without abandoning the remaining sync test.
S20 cleanup and release accountability
CO 09 Preserve cleanup fixes without widening deletion
The latest report says delete_client now cascades governed SOW data for a non-mirror client when hubspot_company_id is NULL, while mirrored clients refuse; two new tests and eight relevant tests passed. It also reports a successful stale Liberty S14b e2e client deletion with a five-table cascade, configurable E2E_MIN_AGE_HOURS defaulting to 24, and the LogRecord key fix from name to client_name. Verify those changes in the released source and retain regression coverage.
A NULL HubSpot company ID alone does not authorize cleanup: genuine manually created clients can also have no source ID. Scheduled cleanup must require trusted test provenance, matching environment/tenant/run ownership and the age threshold. Default to 24 hours; reject malformed or negative ages. A zero-hour sweep is an explicit bounded test operation, never a persistent shared default. Preserve active runs and untagged records, and do not use a “Liberty” name match as the deletion selector.
Use a dry-run manifest and check the real dependency graph, not an assumed five-table limit. Verify mirrored-client refusal, permission boundaries, storage/outbox/task cleanup, repeat safety and no resurrection. S21-01’s protection for projects with activity, timesheets, invoices and actuals must also hold through client deletion; that API cannot become a bypass. An intentional user-authorized client deletion is separate from automated e2e cleanup. Exercise failures in isolation, then confirm exact-run teardown and leak gates.
CO 10 Carry the final human acceptance forward
Record whether FINAL-CLICK was completed on the actual S20 release; the attachment’s rev-62 review does not prove the later image. If missing, preserve that historical status and cover those behaviors in the combined S21 click-through. Do not retroactively label an old revision verified by testing a new one. The user’s report of an S20 merge does not authorize the S21 merge.
The combined review includes real named deals without test leakage, working filters/card destinations, SOW upload and GM, correct reviewers, permanent deletion of a safe fixture, signed delivery/project/actuals, Forecast totals, resource demand and the live sync canary. Keep pending consumer apply, recipient verification, SES production access and BU setup visible with owners. Reuse OP-01–05; never duplicate them as extra “completed features.”
Lead responsibility and execution controls
Before spawning workers, commit a dependency and capacity plan naming the next independently useful task for each role. One worker owns each lane branch/worktree; one writer owns each shared file; one lead owns migration order, Terraform and the deployment lock. Additional worktrees do not create account capacity. On throttling, reduce active workers and resume checkpoints; do not launch replacements in a loop.
Keep S20 carryover, S21 repair, Forecast and operational totals distinct. A single implementation may satisfy several linked requirements, but report the unique scenario count separately from requirement coverage. Record code, local tests, integration, deployment and user acceptance as separate evidence fields within the repository’s reporting states.
Honor session hard stops with a durable checkpoint and exact resume command. Do not deploy incomplete work to meet a fixed minute, force a pass to fit a token budget, or wait for the user to discover predictable conflicts. Inspect current tool authentication; use the supported CLI when gh is unavailable rather than assuming an old login status. Only an affected dependency pauses; unrelated authorized work continues.
S20 carryover acceptance and completion
Add these scenarios to the existing T01–T37 suite. Use S21F:T01–T45 as this contract’s namespace; preserve legacy names such as S20:W1-T33 and S20:t44-full-journey. Extend existing tests where they prove the same behavior; the numbering is a coverage contract, not a requirement to duplicate test code.
Test and scope
Required independent evidence
T38 CO-01/02
Resolve full main SHA, release tag, actual image/digest, stable service and check-only smoke. Reconcile every legacy row, T32/T34 and FINAL-T38. Verify local/staging test selection and complete run counts; no unsupported “all green” or skipped failure.
T39 CO-03
Empty Watching card shows 0. One watched deal in three groups yields exactly one matching row and total across card and list. Unwatch returns 0. Assert identities and access filtering, not only numeric formatting.
T40 CO-04
Mixed review fixture proves distinct in-review SOW package count equals the approvals destination and exact membership. Multiple reviewers do not multiply one SOW; two SOWs under one deal remain two.
T41 CO-05
Execute the formerly skipped legacy full journey through matching signed upload, release, delivery acceptance, one project and known monthly actuals/GM. Reject wrong versions/signatories; retries stay singular. Teardown leaves no leaks.
T42 CO-06
Prove reviewed drift adoption, approved apply and real consumer processing with lag evidence. Exercise stalled/quiet/recovery states and alarm delivery. Link the normal-sync human canary T36; a running task alone does not prove freshness.
T43 CO-07
Rename stage/reassociate source records; verify labels and membership. Interrupt backfill at checkpoint/commit boundaries, resume the same generation and prove complete exact-once effects, no false deletion and safe duplicate/out-of-order processing.
T44 CO-08
Exercise configured, absent, empty and inaccessible BU metadata. Correct display/filter behavior persists on reload; mapped values drive account/company grouping. Record current live property availability separately from synthetic adapter coverage.
T45 CO-09
Test aged tagged fixture, young active fixture, untagged local client, mirrored client and real-name collision. Only authorized eligible targets disappear. Zero-age mode is scoped; failures/retries preserve unrelated records and financial history.

Crosswalk and release evidence
The crosswalk includes original row ID, reported state, observed state, linked CO/S21/FC/OP ID, owner, prerequisite, exact run/revision and remaining human action. CO-10 closes through Gate 5 and FINAL-CLICK evidence. Missing legacy rows are an investigation task, never silently deleted scope. Publish the latest main-image result before declaring S20 deployment closed, and repeat post-merge verification for the eventual approved S21 release.
