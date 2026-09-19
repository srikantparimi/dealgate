# DealGate — complete UI/UX implementation specification

Design handoff · Revision 2 · 19 September 2026 · SmarTek21

This revision was checked against the original 12-page SmarTek21 Deal and Delivery Governance Blueprint and the original user requirements. It corrects the first concept’s weak visibility of NDA/MSA readiness, new-SOW intake, and the complete approval lifecycle. This specification redesigns the application shown in the supplied screenshot. It defines the production experience; the accompanying interactive concept demonstrates representative pages and local interactions with fictitious data. The concept is not connected to HubSpot, your document store, finance data, or authentication. No source repository was supplied or changed.

## 1. Product direction

DealGate should answer four questions without a meeting: **What have we promised? Can we deliver it? Does it meet margin policy? Who must act next?**

Replace the crowded horizontal navigation with a grouped left sidebar. Replace the four enormous empty dashboard boxes with a compact portfolio summary, a prioritized decision queue, and drill-through records. A user should be able to go from an executive concern to the exact SOW, margin version, owner, and required decision in two or three clicks.

Use a distinctive executive workspace: warm neutral canvas, a light navigation sidebar, deep plum executive banner, violet actions, a lime accent reserved for the hero action, and readable financial tables. Functional pages use approval lanes, named decision cards, evidence regions and contextual side panels rather than repeating one generic dashboard layout. Color is supplementary; every status also has a word or icon. Keep visual richness purposeful: editorial typography and a subtle circular motif in the executive banner; no oversized empty cards, misleading readiness scores, or charts without decisions behind them.

Every opportunity is a workspace, rather than a collection of disconnected pages. Its tabs contain scope, commercial assumptions, staffing, documents, approvals, delivery readiness, and history. Advanced administration is outside the daily workflow.

### Non-negotiable business behavior

1. A US delivery component requires at least **35% gross margin**. An India component requires at least **50%**. A mixed engagement must pass each applicable component independently. A combined margin cannot hide an underperforming component.
2. A below-floor component adds a **CEO exception approval** with an explanation of the project, financial shortfall, delivery recommendation, business case, alternatives, and conditions. It does not silently waive functional review.
3. Delivery confirms feasibility and scope; HR confirms staffing and approved loaded costs; Finance verifies the financial model; Legal verifies agreements and terms. CEO exception approval is additional.
4. Approval identifies the exact SOW version, GM version, policy version, and reviewer. Material revisions invalidate affected approvals and create a new package. The server enforces this; UI indicators reflect it.
5. AI output is an indicative planning range with sources, assumptions, confidence, and missing inputs. It cannot become an approved GM, change a policy, or authorize a client commitment.
6. NDA/MSA coverage is verified against the correct legal entities, scope and effective dates. Uploading a file does not prove execution or coverage.
7. Delivery release requires the current internal approvals, any CEO conditions, an executed SOW, and a documented handoff.
8. Renewal follow-up begins two calendar months before SOW expiry and repeats weekly while unresolved. Earlier notice deadlines and short engagements require earlier or immediate attention.
9. Missing financial data is **Unavailable**, **Not validated**, or **Reconciliation pending**. It is never rendered as a confirmed zero.

## 2. Design tokens and visual rules

The default presentation is light, with a light sidebar and a dark plum executive banner. The same workspace also supports dark appearance. Offer System, Light, and Dark appearance under the profile menu. The concept follows the host appearance. Persist appearance independently of financial settings.

| Token | Light | Dark | Usage |
|---|---|---|---|
| Canvas | `#F5F4F8` | `#10101A` | Application background |
| Surface | `#FFFFFF` | `#1A1927` | Tables, panels, dialogs |
| Navigation surface | `#FDFCFF` | `#15131F` | Sidebar only |
| Primary text | `#272337` | `#F2EFFF` | Titles, values, body |
| Secondary text | `#746E82` | `#BAB2CF` | Metadata |
| Divider | `#E9E5EF` | `#383247` | Noninteractive separators |
| Input boundary | `#8F819F` | `#776B8C` | Form controls; distinguish from decorative dividers |
| Primary action | `#7146CE` | `#7957C2` | Main button, selection, links |
| Primary foreground | `#FFFFFF` | `#FFFFFF` | Text on primary actions; verify exact states |
| Primary subtle | `#EFE9FB` | `#32264C` | In-progress review, active context |
| Success text / fill | `#13765C` / `#E7F5EF` | `#77D8B6` / `#163D33` | Approved, verified, reconciled |
| Warning text / fill | `#9A5B0A` / `#FFF4DF` | `#F2C071` / `#3E301C` | Needs decision, due soon, incomplete |
| Danger text / fill | `#BD3446` / `#FCEBEE` | `#FF9BAB` / `#402331` | Below floor, overdue, rejected, failed |
| Executive banner | `#242035` | `#242035` | Title and executive priorities |
| Hero action | `#D8F58C` | `#D8F58C` | Single executive action; text `#24301B` |
| Focus indicator | `#4F46E5` | `#B7B1FF` | Visible keyboard ring against surrounding surface |

Validate contrast for actual text size, foreground/background pair, selected state, hover, disabled state, and dark mode. Do not infer compliance merely from these tokens. Target WCAG 2.2 AA: ordinary text 4.5:1; large text and meaningful control boundaries 3:1. [WCAG 2.2 quick reference](https://www.w3.org/WAI/WCAG22/quickref/).

| Foundation | Specification |
|---|---|
| Typeface | Inter when licensed/available; otherwise system UI sans-serif. No remote font dependency required. |
| Body / table text | 14px, line-height 20–22px; default comfortable density |
| Secondary labels | 12px, line-height 18px; never shrink essential labels to fit |
| Page heading | 32px/38px, weight 600; 28px on narrow screens |
| Section heading | 16px/24px, weight 600 |
| KPI value | 28–32px, weight 600, tabular numerals |
| Weights | 400 body, 500 controls, 600 headings; avoid widespread bold |
| Spacing | 4, 8, 12, 16, 24, 32, 48px |
| Corners | 9px controls; 16px panels; 18px dialogs; 20px executive banner; compact rectangular status badges |
| Shadows | None on routine panels. Small shadow for floating menus; moderate shadow for dialogs. |
| Icons | Lucide, 18–20px, consistent stroke. Text labels on major actions. |
| Buttons | 40px default; minimum 44px effective touch target; 32px compact table action on fine pointers |
| Forms | 40px control; 16px input text on mobile; labels above; help then inline error below |
| Table rows | 52px comfortable; optional 40px compact; user preference, never automatic font shrinking |
| Motion | 120–180ms transitions; reduced-motion support; no looping indicators except real loading |

One primary button per page or decision region. Secondary buttons are outlined; tertiary actions are text. Destructive actions use explicit verbs and an appropriate confirmation. Do not use an unlabeled ellipsis for the main next step.

## 3. Application shell and information architecture

### Desktop composition

Use a 194px navigation sidebar (172px in the 1,024px concept), 70px quiet header and 24–28px content padding. Production can expand the sidebar to 224px on large displays. The command center alone gets a dark plum banner with editorial typography and a lime primary action. Normal working pages use a clear title, task-specific controls and a contrasting white or dark-theme surface.

Header: breadcrumb at left; search, notifications and account at right. Sidebar: product mark and workspace at top; grouped daily workflows; Settings & controls at bottom. Primary actions use violet. Avoid putting NDA, MSA or SOW workflow behind a generic Contracts menu.

| Group | Primary destination | Route | Default screen |
|---|---|---|---|
| Workspace | Command center | `/command` | Executive priorities, client agreement readiness, SOW review lanes and delivery economics |
| Workspace | My work | `/work` | Assigned work, waiting, overdue and completed |
| Growth | Pipeline clients | `/pipeline` | Client owner, commercial stage, NDA, MSA, SOW gate and next check-in |
| Growth | AI discovery | `/discovery` | Functional brief, indicative estimate, evidence and human validation |
| Growth | NDA & MSA | `/agreements` | Entity-level agreement register and lifecycle |
| Commitments | SOW approvals | `/sows` | Six-stage approval board across all SOW packages |
| Commitments | New SOW studio | `/sows/new` | Source/type → scope/terms → GM → routing → submission |
| Commitments | Margin lab | `/margin-lab` | Versioned staffing and geographic margin scenarios |
| Operations | Delivery & actuals | `/projects` | Portfolio, reconciliation, forecast and staffing |
| Operations | Renewals | `/renewals` | Expiry, weekly owner updates, notice deadlines and outcomes |
| Operations | Signed handoff | `/handoffs` | Execution verification, distribution, setup and acceptance |
| Operations | Reporting | `/reports` | Client/SOW economics, revenue basis and process reporting |
| Administration | Settings & controls | `/settings` | General, rates, policy, people, integrations, imports, audit, system health |

Detail routes: `/clients/:id/:tab`, `/agreements/:id/:tab`, `/sows/:id/:tab`, `/sows/:id/reviews/:function`, `/sows/:id/exception`, `/handoffs/:id/:tab`, `/projects/:id/:tab`, `/renewals/:id`, `/discovery/:id`, `/settings/:section`. Lists retain filters and scroll position on Back. The client is the legal/relationship context; every SOW has its own financial model and approval package.

### Migration from existing menus

Dashboard becomes Command center. Deals and Clients are connected through Pipeline clients and Client workspace. Adviser becomes AI discovery. GM sandbox becomes Margin lab plus SOW → Staffing & GM. CEO exceptions become a first-class SOW pipeline stage and dedicated decision page. Approvals become SOW approvals, with My decisions as a filtered view. Actuals sit in Delivery & actuals. Audit, rate cards, policy, legacy import, users and replay move under Settings & controls; replay is labeled Review and retry. Renewals remains a primary destination. Signed handoff becomes a new primary destination because execution, distribution and delivery acceptance must remain visible.

Do not display sprint numbers, internal model names or engineering failure descriptions as business status. Every blocker names the responsible person, next action, due date and evidence required.

## 4. Global interactions

### Search

Header search opens a command dialog using Ctrl/Cmd+K. Input at top; grouped results below: opportunities, clients, contracts, projects, pages. Each result shows name, type, client, status and relevant ID. Search only authorized records. Arrow keys navigate; Enter opens; Escape closes. The trigger retains focus after close. Empty state suggests another client, record ID, or page name. Searching must not expose restricted salaries or inaccessible accounts.

### Notifications and profile

Bell opens a right drawer: Unread / All; filter by approvals, follow-ups, renewals, integration issues. Each item has a clear required action, owner, due time and source record link. Mark read, mark all read and preferences are secondary. Reading a notification does not complete the task. Failed email delivery remains visible to the responsible operator.

Profile menu: name, role, workspace; My profile; Notification preferences; Appearance (System/Light/Dark); Density (Comfortable/Compact); Help; Sign out. A role is not a client-side switch that grants permissions. Administrator access does not automatically grant CEO authority.

### Tables

Toolbar order: saved view, search, filter chips, clear filters; right: columns, export, list/board toggle where relevant. Put multi-select actions in a contextual bar only after selection. Headers sort with direction and accessible state. Numeric columns right-align; align currency and basis in the header; text left-align. Freeze identity columns for very wide grids where needed. Pagination defaults to 25 rows; options 25/50/100. Show result count and filtered total. Server-side filtering, sorting and authorization for production data.

Row name opens the record. Selection checkbox does not open it. Row menu contains secondary actions such as open in new tab, reassign, duplicate scenario, archive draft, and view history as permitted. No bulk CEO approval or bulk signature action without record-level review.

### Forms, drawers and dialogs

Use a right drawer for quick task editing, next steps, contacts, filters and a resource row. Use full pages for SOW/GM editing and decisions requiring side-by-side evidence. Use a centered dialog only for a bounded action or confirmation.

Fields have persistent labels, required indicators, units, examples and contextual validation. Show an error summary linked to invalid fields after submission. Preserve entered values after errors and network failures. Save draft is separate from Submit for review. Unsaved changes warn on exit. A save conflict identifies the other editor and offers comparison, not silent overwrite.

Primary submission states: idle → submitting → success or error. Disable duplicate submissions, use server idempotency, then refresh the authoritative record. Success means the server confirmed the change. Optimistic UI is appropriate for local preferences, not financial approval, signature or release.

### State copy

| Condition | Example | Recovery |
|---|---|---|
| No records yet | “No opportunities yet.” | “Connect HubSpot” or “Create opportunity” if authorized |
| No filter matches | “No opportunities match these filters.” | Clear filters |
| Validated zero | “$0 signed value · No executed SOWs.” | Explain the verified basis |
| Missing model | “GM not validated.” | Open Staffing & GM |
| Source disconnected | “Finance data unavailable. Last successful import: …” | View connection or contact owner |
| Partial dataset | “42 of 48 rows reconciled.” | Review six exceptions |
| Page failure | “We couldn’t load approvals.” | Retry; preserve filters; support reference |
| Stale version | “This package changed after you opened it.” | Compare and reload; prevent approval |
| No permission | “You don’t have access to employee costs.” | Show permitted aggregates; request access |
| No pending decisions | “You’re up to date.” | Recent decisions link; compact empty state |

Loading skeletons match the eventual geometry and have a loading label. Do not show temporary zero KPIs. Errors in one dashboard module should not hide all other healthy modules.

## 5. Command center

The default executive screen must make the original governance problem visible without requiring tab discovery.

1. **Executive banner:** “Every commitment. In view.” Primary action Open approval pipeline. Four concise measures: known open-pipeline value, SOW packages in progress, clients with agreement gaps, and CEO decisions pending. Label sample/freshness and financial basis. Do not invent a health score.
2. **Priority signals:** a CEO exception, a pending MSA signature, and an approaching renewal. Each is a whole clickable region with client, reason, owner/deadline and direct destination.
3. **Pipeline-client readiness table:** client/owner and commercial stage; separate NDA and MSA statuses; current SOW gate/package versions; next client action. Agreement states open the actual agreement record. This table must be above the fold or immediately after the priority signals at desktop height.
4. **SOW approval preview:** Scope & GM, Functional review and CEO exception lanes; each card shows client, engagement, value, margin, agreement states, four functional review markers, accountable owner and next action. All stages opens the complete board.
5. **Delivery economics:** approved versus forecast margin for active signed SOWs, geographic floor and variance, with drill-through. Distinguish signed value from open pipeline and recognized revenue.

Role-specific landing priorities remain available: Sales/Marketing sees qualification and follow-ups; Delivery sees technical reviews and risk; HR sees staffing/cost validation; Finance sees GM/reconciliation; Legal sees agreement/SOW blockers; executives see cross-functional exposure. Roles are server-authorized identities, not a client-side privilege switch.

Pipeline is uncontracted proposed value. Signed value is full selected contract value. Portfolio GM is total gross profit divided by total revenue on the same reporting basis. Unknown amounts are excluded with an explicit count; never silently displayed as confirmed zero. Every metric opens its supporting records.

## 6. My work

Tabs: **Assigned to me / Waiting on others / Overdue / Completed**. Filters: task type, client, owner, due range, priority. Header action: Create task.

List row: checkbox only for manually completable tasks; task title; linked record; type; assignee; due date and overdue age; status; primary next action. Approval and signature tasks complete through the underlying workflow, never a generic checkbox.

Task drawer: title, record, description, owner, due date/time, priority, checklist, comments, attachments, history. Actions: Save; Reassign; Complete/Reopen where permitted. Required client follow-up needs an outcome and a next date or final disposition. Overdue tasks escalate to the owner’s manager according to configured rules.

## 7. Pipeline clients and opportunity intake

This is the daily Sales/Marketing/Legal view. Agreement readiness is mandatory in the default layout.

Filters: **All clients / Agreement gaps / Ready agreements / Follow-up due**; client/owner search; production adds commercial stage, next-action date, business unit and saved views. Header action: New opportunity.

Default columns, in order: **client and account owner; HubSpot commercial stage; NDA status; MSA status; SOW count/current governance gate; next client action and date**. On wider screens add proposed value, delivery owner and last sync. NDA and MSA are separate clickable statuses, never one combined Contracts checkbox.

Supported agreement states: Missing, Requested, Drafting, Under review, Sent for signature, Partially signed, Executed, Expired, Terminated and Superseded. The concept labels a sent agreement “Awaiting signature”. These display labels map to explicit lifecycle states. A Missing owner is visible and creates an assignment task. An agreement awaiting client signature must not appear as legally ready.

Each client opens a workspace with Overview / Agreements / Opportunities & SOWs / Contacts / Financials / Activity. Show multiple SOWs under one client without overwriting their independent approval histories. Entity coverage can differ across the same commercial account.

New opportunity fields: client display name; legal entity or existing entity lookup; HubSpot association; account owner; functional requirement; engagement type; delivery model; planning value/currency (Unknown allowed); target start/end; expected close; next action/date. The quick concept uses the essential subset; production uses progressive sections, not a giant undifferentiated form. New entities start with Missing NDA/MSA until verified evidence is associated.

HubSpot is authoritative for opportunity identity, commercial stage and CRM owner. DealGate is authoritative for agreement coverage, SOW/GM versions, governance and release. Show last sync, conflicts, unassigned records and failed updates. Retry and reconciliation must not create duplicate opportunities or tasks.

## 8. Opportunity and SOW workspace

Persistent header: client → opportunity name; ID, owner, engagement type, delivery model, dates, SOW and GM versions. Below: compact NDA, MSA, scope, financial and approval statuses. Right primary action changes with the next valid step: Complete scope, Build GM, Submit package, Resolve review, Review exception, Prepare signature, or View handoff. An always-visible readiness panel explains blocked actions.

A client/opportunity may contain several SOW packages. Open a SOW as a dedicated workspace with its own version identity and approval progress. The SOW header includes client, legal entity, value, type, owner and exact SOW/GM versions. Six clickable progress steps are always visible: Intake, Scope & GM, Function reviews, CEO exception (conditional), Signature and Handoff.

SOW tabs: **Approvals / Scope / Staffing & GM / Agreements / Documents / Signature / Handoff / Activity**. Approvals is the default for an in-review SOW; scope or intake is the default for a new draft. The table below retains the broader opportunity information model; SOW-specific tabs split agreement, signature and handoff controls into explicit destinations.

Tabs and exact contents:

| Tab | Main content | Actions |
|---|---|---|
| Overview | Commercial summary; owner/next action; readiness checklist; key risks; recent decisions | Update next step, assign owner, open blocking item |
| Scope | Outcomes, deliverables, exclusions, assumptions, dependencies, acceptance, risks, client inputs | Edit draft, request Delivery validation, create scope revision |
| Staffing & GM | Model version selector; staffing grid; costs; geography tests; scenarios | Add resource, compare, save draft, submit model, export GM |
| Documents | Relevant NDA/MSA/SOW/amendments with coverage, version and execution state | Upload, review, compare, prepare signature |
| Approvals | Current package, function-by-function review, comments, CEO exception if required | Submit, withdraw draft, respond, open review |
| Delivery | Readiness, staffing commitments, kickoff, handoff checklist, linked project | Prepare handoff, verify conditions, release when permitted |
| Activity | Chronological changes, decisions, files, client updates, sync events | Filter, inspect diff; authorized export |

Scope editing uses structured lists, not a single unrestricted paragraph. Required fields depend on engagement type. Delivery sign-off identifies assumptions; unknown integrations, acceptance criteria or availability remain visible risks. A proposed budget cannot masquerade as an approved delivery estimate.

## 9. Staffing & GM workspace

At top: **Approved baseline / Current draft / Scenarios** with version selector and Compare versions. An editable draft is visually distinct from an approved read-only model. Show “Draft · Not approved for commitment” beside its version.

Next: revenue, delivery cost, gross profit and combined GM; below, independent US and India policy tests. The combined result is informational. Show Not applicable for a location not used, rather than treating it as zero revenue.

Staffing grid columns: role, location, grade/skill, resource or TBD, start/end, allocation, quantity, billable hours/days, bill rate, loaded cost rate, revenue, delivery cost, GM. Restricted users see approved role costs or aggregates instead of employee compensation. Row drawers expose burden components only to authorized HR/Finance roles.

Cost sections: staffing; contractors; agreed benefits/payroll burden; recruiting or setup costs when included by Finance policy; delivery management; licenses/cloud/vendor charges; travel; contingency. Show the approved cost definition, rate-card version, FX source/date, and included/excluded tax treatment. Finance owns the calculation policy; never change it through an AI estimate.

Revenue sections: fixed fee and milestone allocation; time-and-materials hours/rates/cap; recurring service price/term; one-time charges; discounts; credits. Finance confirms the geographic revenue allocation. Unallocated shared revenue/cost is an incomplete model, not permission to pass a blended check.

| Engagement | Required specialized fields |
|---|---|
| Single-person staff augmentation | Role, location, start/end, rate unit, billable calendar, loaded cost, overtime, replacement assumptions |
| Multiple-resource staff augmentation | Resource rows, overlapping dates, allocation, overtime and capacity conflicts |
| Fixed-price project | Deliverables/milestones, effort, staffing mix, dependencies, contingency, change assumptions |
| 2- or 4-week assessment | Duration, workshops, roles, effort, output artifacts, fixed fee and explicit exclusions |
| Managed service | Coverage hours, volume assumptions, team, term, SLAs, recurring revenue/cost and service risk |
| Placement / permanent hire | Distinct template only if this is the actual engagement; fee/replacement/refund model and Finance-approved cost basis; do not confuse with one-person staff augmentation |

Calculation: `GM = (revenue − eligible delivery cost) / revenue`. Minimum revenue at a floor is `cost / (1 − floor)`. Use decimal money arithmetic and full precision for policy evaluation; round only for display. Zero/negative revenue needs explicit Finance handling; a missing cost never becomes zero by default.

For the illustrative Northstar model: US revenue $90,000, cost $65,000 → 27.777…%, shortfall 7.222… percentage points. India revenue $55,000, cost $30,000 → 45.454…%, shortfall 4.545… points. Combined revenue $145,000, cost $95,000 → 34.482…%. Minimum compliant price with the same costs and the stated geographic allocation model is $100,000 US + $60,000 India = $160,000. Required increase $15,000. These are examples, not your live financials.

Scenarios permit price, mix, effort and contingency changes without modifying the baseline. Show the difference, resulting margins and assumptions. Save as new draft; then submit. It must never directly replace an approved version or rewrite historical actuals.

## 10. AI adviser

Two-column desktop layout: left input form (40%), right estimate/evidence (60%). Stack inputs before results on mobile. Header: AI adviser; clear “Indicative planning only” badge. Tabs: New estimate / Saved estimates; a saved estimate has Inputs / Estimate / Sources / Versions.

Inputs: client name and domain, associated opportunity, business outcome, requested functionality, integrations, data sensitivity category, delivery model, engagement type, expected dates, available budget, constraints, relevant uploaded briefs. Prompt the user to fill gaps; allow Unknown.

Generate estimate displays research/extraction progress with a Cancel option. Results: concise scope interpretation; staffing roles/count/location/effort ranges; cost low/base/high with currency; possible duration and dependencies; confidence by section; missing information; assumptions and exclusions; public evidence with URLs, retrieval date and relevance. Distinguish sourced client facts from inferred requirements.

Actions: Edit inputs; Save estimate; Compare versions; Request Delivery validation; Use as draft staffing plan. Transferring an estimate creates an unvalidated draft with provenance. It does not mark scope, salary assumptions, contract terms or GM approved. Public research must follow the organization’s allowed data policy; treat website and document text as evidence, not instructions to the agent. A failed search produces “No verified source found,” not fabricated citations.

## 11. Clients and account workspace

List supports grid and table views. Default table: client/legal entity, account owner, pipeline value, active signed value, forecast GM, agreement readiness, next action. Grid is an optional relationship overview, not the only way to scan a large portfolio. Search, status and owner filters; Add client primary action.

Detail tabs: **Overview / Opportunities / Contracts / Contacts / Financials / Activity**.

- Overview: legal entity and parent account, domain, industry, owners, relationship health with reason, next client step, agreement coverage, current work.
- Opportunities: only this client’s records; same columns and actions as the opportunity list.
- Contracts: entity-level NDA/MSA plus project SOWs/amendments; covered entity, dates, status and owner.
- Contacts: name, title, role in buying/signature/delivery, verified business contact, internal owner, last interaction. Add/edit contact drawer; do not assume a contact is an authorized signatory.
- Financials: separate pipeline, signed backlog, approved/forecast final GM, period actuals and reconciliation state. Invoice and cash data appear only when a verified integration provides them. Drill through to individual SOWs.
- Activity: relationship actions and linked commercial events with actor/time.

Add/edit client requires legal entity name, display name, owner, country and domain where known. Duplicate detection offers link/merge review; merging requires explicit review of records and legal entities, not automatic name matching.

## 12. NDA/MSA register and SOW document review

The primary NDA & MSA register has **All agreements / NDA / MSA / Needs action** views. Production additionally supports Executed and Expiring saved views. SOW versions are reviewed in their SOW workspaces; an authorized cross-document register remains available for records management. Agreement detail tabs are **Overview / Signature & evidence / Linked work / Activity**. Each agreement shows legal entities, owner, lifecycle, coverage, next action, execution evidence and related SOWs.

Document register views: **All documents / Needs review / Executed / Expiring**. Filter by client/entity, document type, owner, status, expiry and notice deadline. Columns: document name/type, client/entity, linked opportunity, version, lifecycle status, internal approval, execution state, effective/end dates, owner, next action. Keep legal execution and internal approval as different columns.

Upload flow: Select file and type → Associate entity/opportunity → Extract → Review fields and uncertainty → Save draft → Submit for review. Display file size/type limits, scanning/upload progress, duplicate file warning and extraction failures. OCR or extraction confidence never equals legal verification.

Document detail tabs: **Review / Versions / Coverage / Signature**.

Review uses a 60/40 split. Left: document preview, page navigation, zoom, download original and search. Right: extracted title, entities, term, scope, fee, currency, milestones, payment terms, acceptance, renewal/notice terms, governing agreements and verification status. Clicking a field highlights its source page/text; legal comments have owner and resolution. Never invent a document preview or verified quote when extraction failed.

Versions: version, uploaded by/time, checksum/identity, draft/executed designation, associated approval package. Compare documents plus extracted field differences. Executed originals are immutable.

Coverage: NDA/MSA relationships, party names, dates, scope, geography, superseding documents, unresolved gaps and Legal verifier. Show Unknown coverage distinctly from Missing agreement.

Signature: exact approved document/version; verified signatories; delivery channel; sent/viewed/signed/declined/expired states; execution evidence; completion timestamp. Send for signature is gated by current approvals and required CEO conditions. External delivery requires approved recipients and production authorization. After execution, distribute the signed SOW and handoff pack to the account owner and authorized leadership, with delivery outcome logged. Do not interpret a locally uploaded filename containing “signed” as proof.

## 13. SOW pipeline, guided intake and functional approvals

### Complete approval board

The SOW approvals screen has six lanes: **Draft intake / Scope & GM / Functional review / CEO exception / Client signature / Handoff**. At 1,024px the concept uses two rows of three lanes, preserving readable cards. At tablet use two lanes per row; at phone use one. Production may offer a horizontally scrollable desktop board only with an equally usable list view and keyboard alternative.

Filters: All packages, Blocked, My decisions and New drafts; production also filters client, type, reviewer, age and owner. Do not permit drag-and-drop to bypass gates. “My decisions” reflects authenticated assignment. The concept is an executive sample and maps it to pending CEO work.

A card contains engagement type, stage age/due, client, SOW name, proposed value, margin/completeness, separate NDA/MSA states, Delivery/HR/Finance/Legal mini-statuses, owner avatar/name, and the actual next action. Value, status and gate counts derive from records. SOW title opens the record; no generic record fallback.

### New SOW studio — five steps

| Step | Main work area | Readiness side panel | Advance rule |
|---|---|---|---|
| 1. Source & type | Client/entity, SOW title, file selection, source validation and engagement templates | Client owner, NDA, MSA, model selection | Client and title present; file is staged or structured draft chosen |
| 2. Scope & terms | Verified scope, deliverables, price/currency, term, acceptance, exclusions, payment/notice/signatory fields | Missing critical fields and agreement gaps | Commercial facts complete enough to cost; uncertainty remains explicit |
| 3. Build GM | Engagement-specific staffing/cost model, revenue, effort, direct costs, geographic allocation and floor checks | Model version, rates/FX sources, geographic policy result | No missing cost/location/allocation; model remains unvalidated until reviewers approve |
| 4. Review routing | Named Delivery, HR, Finance and Legal owners, due dates, conditional CEO route | Owner assignment and package completeness | Required accountable reviewers assigned; routing acknowledged |
| 5. Submit package | Frozen SOW/GM versions, commercial summary, scope, agreements, review plan | Final blockers and permitted next action | Submission creates a Delivery review task; it does not approve the contract |

Templates: multiple-person staff augmentation, single consultant, fixed price, assessment (including two/four weeks), time and materials, managed service. A permanent placement is a separately configured business model, not a synonym for one consultant. Assessments include prep/workshops/analysis/reporting/travel and sponsor review. Mixed models show separate revenue and cost for US and India; total revenue/cost are derived from these allocations. The production grid contains resource rows, periods, units and contingencies as specified in section 9.

The concept can load an explicitly illustrative SOW. Uploading a real file in the concept only selects it; it does not claim extraction occurred. Production needs upload security, duplicate checks, extraction/OCR, source references and human field verification before submission.

### Named functional review cards

After the Delivery baseline, show four decision cards in a two-column layout. Each has function icon/title, status, reviewer, deadline/age, exact package versions, review responsibility and action. Delivery: scope/effort/capacity/acceptance. HR: cost/availability/start dates. Finance: revenue allocation/cost/margin/cash. Legal: entities/coverage/terms/signatories.

Delivery establishes the technical baseline and staffing assumptions. HR, Finance and Legal review the frozen package concurrently once the baseline is ready. HR cost assumptions used by Finance must be verified; any changed cost produces a new financial version. The progress display must not imply that completing one function completes the others.

Click Review package for a focused review with Summary / Financials / Scope / Documents / History. Show current function-specific checklist, evidence, reviewer, requester and due date. Actions: Approve / Request changes / Reject. Require reasons for rework/rejection and reviewed evidence for approval. Completed reviews open read-only decision evidence. Each action identifies exact versions and protects against concurrent changes.

Legal approval cannot complete when required coverage remains missing, expired, unresolved or unsigned unless an expressly approved alternative Legal policy applies. Functional approval cannot skip a missing technical baseline. Missing required cost data prevents Finance sign-off. When all functional reviews complete, evaluate the unrounded geographic margins: any failure enters CEO exception; otherwise the package moves to signature readiness.

### Signature and handoff visibility

Signature tab shows separate checks for NDA/MSA coverage, four functional approvals, required CEO exception and validity, pre-signature conditions, exact outgoing document version and verified signatories. Show why Send is held; do not merely disable a button without explanation. A sent envelope shows client execution state and follow-up, not a second invitation to send a duplicate.

Handoff tab links to execution verification, distribution recipients/receipts, account/Delivery acknowledgement, billing/PO/staffing setup and renewal creation. Signed handoff is also a primary destination for operational users. No phase is marked complete solely because the CRM opportunity was won.

## 14. CEO margin exception

This is a dedicated decision page, reached from Overview, Approvals or the opportunity. It must explain the project before asking for a decision.

Top metrics: proposed revenue; eligible cost; expected profit/combined GM; price gap to policy. Below, a full-width geography table: location, allocated revenue, cost, proposed GM, required GM, shortfall in percentage points and compliant revenue. Both under-floor components remain visible.

Left main column: project outcome and scope; why the exception is requested; business rationale; client constraints; contracted versus speculative future value; alternatives considered; delivery feasibility; HR recommendation; Finance recommendation; Legal status; downside sensitivity; recovery plan and mitigation owners; evidence links. Right column: decision state, approvable package versions, required conditions and decision actions.

Actions: **Approve exception**, **Approve with conditions**, **Request changes**, **Decline**. The concept emphasizes conditional approval; the production workflow supports all four. Rationale is required for every final decision. Conditional approval requires individual conditions, each with owner, due date, evidence requirement and whether it blocks signature, delivery or later milestones. A free-text note alone is insufficient.

Record: CEO identity, time, decision, business rationale, SOW/GM/policy versions, scope of exception, authority, approval-use expiry, conditions and evidence. Decline routes back to reprice/re-scope or close lost. Rework creates a revised package. An expired, superseded or withdrawn exception cannot authorize signature. A CEO decision cannot remove Legal restrictions or waive unrelated release requirements. Concurrency protection prevents approving a package changed in another session.

## 15. Projects & actuals

Portfolio tabs: **Portfolio / Actuals / Staffing**. Header actions: Import actuals where authorized; secondary Export. Filters: client, delivery owner, geography, status, period and data completeness.

Portfolio columns: client/project, SOW/end date, delivery owner, signed value, approved final GM, forecast final GM, variance in percentage points, risk, next review. Show baseline versus forecast with the same scope/term. Default sort highlights deterioration and overdue updates, not merely largest revenue.

Actuals tab: period picker and import status; reconciled revenue/cost/GM; rows by SOW with missing data, adjustments and reconciliation owner. Actions: Upload, preview/match, resolve exceptions, approve reconciliation, inspect source. Partially reconciled periods remain labeled. Prevent duplicate postings using source keys and import identity.

Staffing tab: weekly resource capacity and approved/proposed allocation with conflict flags. Filter role, location, skill and delivery owner. Open a resource drawer showing committed work and availability appropriate to role. Proposed staffing does not authorize employment or an external commitment.

Project detail tabs: **Overview / Financials / Staffing / Risks & changes / Activity**.

- Overview: signed scope, delivery/account owners, dates, milestones, next client action, risks and release evidence.
- Financials: approved baseline; current forecast (cost incurred plus cost to complete); period actuals; reconciliation; geography tests; drill-through line items. Change forecast requires rationale and new forecast version.
- Staffing: named/proposed resources, allocation, dates and approved changes.
- Risks & changes: risk description, probability/impact, owner, mitigation and review date; change requests with scope, price, margin and schedule impact, approvals and amendment linkage.
- Activity: forecasts, reconciliations, staffing changes and decisions.

Forecast margin falling below a floor opens a recovery decision and, where commercial exceptions are needed, an additional CEO review. It does not retroactively overwrite the original approved GM. Report original baseline, approved amendments and current forecast separately.

## 16. Renewals and weekly owner follow-ups

Tabs: **Action required / Weekly follow-ups / Upcoming / Closed**. The weekly view lists trigger date, reminder event, owner, delivery outcome and recorded response. Optional timeline/list switch. Columns: client/SOW, owner, signed value at risk, expiry, contractual notice deadline, days remaining, last client update, next action/date, renewal stage, health.

Click a row for a renewal workspace: agreement summary; expiry/notice logic; account and delivery owners; client engagement timeline; proposal/amendment; next step; reminders and escalation; final outcome evidence.

Actions: Record update; Schedule next step; Assign owner; Create renewal opportunity; Link replacement SOW; Close out. Outcomes: discussion in progress, proposal requested, negotiation, extension signed, replaced, not renewing, completed closeout. “Client interested” is not a signed renewal.

Reminder calculation uses calendar months in the contract’s business timezone: expiry 15 November → first standard alert 15 September. For month-end dates, clamp to the last valid day. Repeat every seven days while unresolved. If contractual notice needs earlier action, schedule that separately with an earlier visible due date. If created after the first alert date, surface immediate review. A two-week assessment should not wait for a nonexistent two-month lead window.

Logging an update preserves the next weekly review unless a configured, visible rule defers it. Snooze requires reason and a next date; it cannot silently pass a contractual notice deadline. A final outcome with uploaded evidence first enters verification. Stop unresolved-expiry reminders only when an authorized reviewer verifies the outcome and closes the workflow; retain any handoff/closeout tasks. Alert history shows attempted, delivered, failed and acknowledged states.

## 17. Reports

Tabs: **Portfolio / Margin / Revenue / Renewals / Approval turnaround**. Filters across top: period, business unit, geography, client, account owner, engagement and currency; each report adds its relevant filters. Display basis, as-of time, included/excluded counts and completeness. Export retains these metadata and access restrictions.

| Report | Contents and drill-through |
|---|---|
| Portfolio | Pipeline by stage, active signed work, decisions and delivery risk; click a segment for records |
| Margin | Approved final vs forecast final vs period actual, by SOW/client/geography; below-floor exceptions and recovery owners |
| Revenue | Contracted value, forecast revenue, period recognized revenue, backlog, invoice/cash only if sourced; never combine them as “Revenue” |
| Renewals | Expiring value by month, notice deadlines, owner response, renewal outcomes; distinguish original and replacement contracts |
| Approval turnaround | Median and tail elapsed time, outstanding age, function/owner, rework loops; show clock basis and pauses |

Use simple bars/lines and a data table; no decorative pie charts for near-identical values. Display meaningful units, readable legends and accessible summaries. CSV exports are available where authorized; PDF review packs include definitions and data freshness. Scheduled report delivery must use verified recipients and production permissions.

## 18. Settings & controls

Settings has a secondary vertical navigation inside the main region. Each section is a real route. Hide unauthorized sections; the server independently checks access. Policy changes and historical data edits are never casual switches.

### General

Fields: workspace name, legal entities, reporting currency, business timezone, fiscal calendar, working calendars, defaults and notification routing. Save preferences separate from governed financial policy. Explain which settings affect future records and which are only display preferences.

### Rate cards

Tabs: Current / Scheduled / Archived. Columns: role, grade, geography, employment type, cost/bill rate, currency/unit, effective interval, version, approval status. Actions: Create version, import, compare, submit, activate when approved. Effective periods cannot overlap ambiguously. A new rate card does not retroactively change an approved GM. Restrict compensation-level fields.

### Margin policy

Read-only current policy summary: US35%, India50%, mixed-component rule, cost definition, allocation requirement, exception authority. Tabs: Current policy / Pending changes / History. Propose change opens a structured form with values, reason, effective date, scope and impact preview. Governed approval and versioning precede activation. Display which current packages would need re-evaluation. An ordinary administrator cannot lower a floor to avoid CEO review.

### People & access

Tabs: Users / Roles / Delegations. User table: name, work email, role, account/business-unit scope, status, last access. Actions: Invite, edit scoped access, deactivate, review. Role detail lists view/edit/approve/export capabilities and sensitive fields. Delegation includes function, delegate, scope, start/end, reason and authority. Preserve the original reviewer and delegate in history. Deactivation reassigns open work through a reviewable queue.

### Integrations

Cards/list for HubSpot, identity, document storage/signature, Finance and notifications. Status, authorized scope, owner, last success, lag and errors. Open detail: Connection / Field mapping / Sync history / Failure handling. Actions: Connect via authorized flow, test, inspect mapping, retry safe failures, disconnect with impact warning. Never display tokens in the UI. An unconfigured connector shows setup steps, not fake green health.

### Data imports

Tabs: New import / In progress / Completed / Needs attention. Flow: upload → map → validate → preview differences → confirm → reconcile. Row-level errors are downloadable with reasons. Legacy approvals require provenance and legal/finance verification; label uncertain records “Imported · Evidence unverified”. Do not manufacture historical approvals. Keep reversible staging before committing. Show duplicates, unknown entities, missing currencies and unresolved dates.

### Audit log

Filters: actor, time range, entity, action, client, record. Columns: when/timezone, actor, action, target, result. Detail drawer: before/after values, reason, version, related decision, source/correlation ID visible to authorized operators. Immutable history; exports respect sensitive-field access. Routine users see relevant activity in record tabs without needing this administrator view.

### System health

Tabs: Overview / Failed events / Notification delivery / Reconciliation. Show real service/queue health only if available. Failed event detail explains the business effect, record, previous attempts, error class, current state, proposed retry and duplicate protection. “Review and retry” opens a preflight; it does not blindly replay a signed contract distribution or duplicate an approval. Record the operator, outcome and side effects. Raw payloads are restricted and redacted.

## 19. Authorization and safe disclosure

| Capability | Primary owner | Other access |
|---|---|---|
| Intake and opportunity update | Sales / marketing | Account team within scope |
| Feasibility, effort and delivery plan | Delivery | Sales can propose; Delivery validates |
| Named staffing and loaded cost | HR / authorized Finance | Delivery sees approved role costs as permitted |
| GM verification and reconciliation | Finance | Leaders see authorized aggregates |
| NDA/MSA/SOW legal verification | Legal | Account owner sees readiness and permitted documents |
| Below-floor exception | CEO or explicitly governed delegate | Others prepare/recommend; cannot self-approve |
| Delivery release | Designated release owner after all gates | Server validates current evidence |
| Workspace operations | System administrator | Does not imply business approval authority |

All APIs, exports, search results, notifications and document downloads enforce the same scope as the UI. Masking cells in the browser is insufficient. Approval records need a real accountable identity. Do not automatically grant every executive employee-level salary visibility.

## 20. Responsive behavior and accessibility

- Wide desktop: full sidebar, two-column evidence/decision regions, four KPI columns, full tables.
- Tablet: collapsed navigation or drawer; two KPI columns; stack evidence and decisions when reading width is insufficient; retain record identity and primary action.
- Mobile (320px and up): menu button opens navigation; one-column forms; two small KPIs only when they remain readable; full-width decision actions; label all icons. Tabs wrap or use a clearly labeled section selector. Never shrink table text to fit.
- Financial grids may scroll horizontally inside a labeled region; keep identity and key status available. Offer a concise card/summary view for mobile review. Do not require dragging.
- Dialogs fit viewport, trap focus, close on Escape where safe, and restore trigger focus. Long financial editing belongs on a full page. A sticky action bar must not obscure content or focused inputs.
- Use semantic headings, landmarks, labels, real buttons/links, table headers, accessible tabs and status announcements. Keyboard navigation covers search, menus, tab lists, tables, dialogs and decisions.
- Errors name the problem and recovery. Status changes use live announcements without reading the entire page. Color always accompanies text. Tooltips supplement rather than replace essential guidance.
- Test 200% zoom, 320/375/768/1024/1440px widths, high contrast, reduced motion, keyboard-only and a screen reader. Validate both themes and actual displayed data, including long legal entity names and large negative values.

## 21. Implementation framework and component structure

Preserve the existing application, router, authentication and backend unless repository inspection reveals a concrete reason to change them. A visual redesign does not justify rebuilding working business services.

For a React application, use TypeScript, the existing supported React version, Tailwind or equivalent token-driven CSS, and **shadcn/ui** components with one consistently chosen accessible primitive family. The sidebar primitives support a composed navigation shell. [Official shadcn sidebar documentation](https://ui.shadcn.com/docs/components/base/sidebar).

Use the framework as infrastructure; implement the custom shell, editorial banner, readiness matrix, approval lanes, review cards, studio and evidence side panels as designed. A default component-library dashboard does not satisfy the visual brief.

Recommended supporting pieces: the existing query/cache layer; TanStack Table when advanced grids need controlled sorting/filtering/selection; React Hook Form with schema validation where already compatible; Lucide icons; the existing chart library with accessible summaries. Pin compatible versions after inspecting the repository. Do not introduce overlapping form, table or styling systems just to match this list.

Suggested component boundaries:

- `AppShell`, `PrimaryNavigation`, `WorkspaceHeader`, `GlobalSearch`, `NotificationDrawer`, `ProfileMenu`.
- `PageHeader`, `RecordHeader`, `RecordTabs`, `Metric`, `StatusBadge`, `ReadinessChecklist`, `EmptyState`, `ErrorState`, `SourceFreshness`.
- `DataTable`, `FilterBar`, `SavedViews`, `ColumnPicker`, `Pagination`, `RowActions`, `MoneyCell`, `MarginCell`.
- `OpportunityWorkspace`, `ScopeEditor`, `StaffingGrid`, `GMVersionSelector`, `GeographyMarginCheck`, `ScenarioCompare`.
- `DocumentReview`, `ExtractedField`, `DocumentVersionCompare`, `CoveragePanel`, `SignatureTimeline`.
- `ApprovalPackage`, `FunctionalReviewChecklist`, `CEOExceptionReview`, `ConditionEditor`, `DecisionHistory`.
- `ProjectFinancials`, `ActualsReconciliation`, `RenewalWorkspace`, `ReminderHistory`, `AuditDiff`.

Shared state contracts must distinguish pending/unavailable/zero and draft/approved/executed. Use explicit money currencies and units, ISO timestamps, contract business timezone, stable IDs and version IDs. Use server-calculated authoritative financial results. Keep UI calculation previews marked until verified.

## 22. Implementation sequence for the coding agent

1. Inspect current routes, roles, APIs, data contracts and existing tests. Map every current capability to the new navigation. Record gaps before editing.
2. Implement tokens, typography, shell, navigation, headers, status language, forms and shared table patterns. Replace technical placeholder copy.
3. Implement the full opportunity workspace, scope editing, engagement-specific GM, geography checks and version comparison.
4. Implement document review, coverage, current-package approvals, CEO exception conditions and signature/release readiness.
5. Implement project actuals/forecast, reconciliation, change control, renewals and owner follow-ups.
6. Implement role-specific overview, reporting, AI adviser evidence and validation handoff.
7. Implement settings, access, rate/policy versions, integrations, imports, audit and safe retries.
8. Complete real user-journey testing, accessibility, responsive verification and regression fixes. Produce a gap/evidence report.

Work may proceed in independent streams after shared contracts are agreed. A blocked external integration should use an explicit development adapter with contract tests while other work continues; production must show the integration as unavailable. Never declare a blocked business gate completed because its UI exists. Do not remove checks to make tests pass.

## 23. Acceptance journeys and release evidence

These are user behaviors to test end to end, not assertions that components resemble their implementation.

| Journey | Required outcome |
|---|---|
| Marketing researches an incomplete opportunity | Missing inputs visible; public evidence attached; estimate remains indicative; Delivery validation task created |
| HubSpot creates a deal without an owner | Assignment exception visible; no owner invented; updates are idempotent and auditable |
| Sales prepares a four-week US assessment at 35% | Exact boundary passes when inputs complete; functional review still required |
| India-only engagement at 49.999% displayed as 50.0% | Policy fails at full precision; CEO route required despite rounded display |
| Mixed model blended margin looks acceptable but US is below35% | US exception shown; blended result cannot authorize release |
| Both components below floor | One package presents both shortfalls and coherent CEO business case |
| CEO approves with conditions | Correct versions/identity recorded; required pre-signature conditions still block signature |
| CEO declines or requests changes | Deal returns to actionable reprice/re-scope path with reason and owner |
| Price changes after Finance and CEO approve | Old approvals stay historical; new package requires the right reviews; signature blocked |
| User approves stale package in another tab | Server rejects with version conflict; UI preserves comment and offers comparison |
| NDA/MSA belongs to another legal entity | Coverage remains unresolved; Legal action required |
| Unsigned or duplicate SOW uploaded | Not executed merely because of upload/name; version and duplicate checks visible |
| Signed SOW is completed | Correct signed version and handoff sent to authorized recipients; delivery outcomes recorded |
| Forecast deteriorates after delivery begins | Baseline preserved; updated forecast/recovery/exception workflow visible |
| Finance imports duplicate/partial actuals | Duplicate costs prevented; partial reconciliation never labeled final |
| Two-month reminder crosses month end / leap year | Correct calendar date/timezone and weekly repeats; duplicate reminders prevented |
| Contract has an earlier notice deadline | Earlier action surfaced; normal expiry schedule does not hide notice obligation |
| Two-week assessment is created today | Immediate renewal/closeout review if already inside the lead window |
| Renewal update says extension signed without evidence | Completion rejected or left pending verification |
| Restricted user searches/exports another account or salary data | No data leakage through UI, API, export, URL or notification |
| Network fails while approving or sending signature | No false success or duplicate side effect after retry |
| Mobile executive reviews a long exception | All evidence and decision controls usable without clipping or tiny text |
| Keyboard/screen-reader user completes a review | Logical focus, labels, tabs, dialogs, errors and announcements work |
| Empty workspace or disconnected Finance source | Honest empty/unavailable states; no fabricated zeros or green health |

Automate the critical journeys with real browser tests against a controlled seeded environment and verified test doubles for external delivery. Add service/integration tests for precision, version gates, authorization, idempotency and scheduling. Use targeted unit tests for pure financial/date functions and state transitions. Include contract tests for HubSpot, signatures and financial imports. Supplement automation with role-based user acceptance sessions and accessibility inspection. Document actual results, screenshots/traces, known gaps and outstanding external configuration.

## 24. Scope and verification of the revised concept

The V2 concept makes these previously under-exposed requirements directly interactive: pipeline-client NDA/MSA status; individual agreement records; a six-lane SOW approval board; five-step intake with engagement selection and single/mixed-location GM; named functional decisions; additional CEO exception with rationale and structured condition; signature gating; signed-SOW distribution and delivery acknowledgement; weekly renewal history; and AI evidence/validation views. Existing delivery, finance, reporting and administrator layouts are retained under the new visual system.

The sample contains six pipeline clients totaling $680,000 of proposed value. Three clients have agreement gaps: Atlas MSA awaiting signature, Beacon NDA expired, Cedar NDA requested/MSA missing. Northstar requires a CEO exception; Harbor is in Finance review; Vista is awaiting client signature. Separate active delivery samples are Meridian and Summit. All names, records and financial figures are illustrative.

The prototype executes local interactions only. Upload/extraction, source research, HubSpot sync, e-signature, recipient messaging, scheduled notifications, access control, permanent persistence and detailed accounting remain production implementation requirements. Secondary operational forms preview the design. Some illustrative agreement evidence and past decisions are seeded sample states, not real verifications.

JavaScript syntax and ten non-browser user-journey test groups passed. A traversal rendered 36 primary page/tab states without runtime errors. Tests covered the new mixed-location SOW journey, all four functional decisions, CEO routing, condition evidence, Legal coverage blocking, material revision invalidation, renewal outcome evidence and signed handoff. See the validation report for exact method and limits.

No rendered browser screenshot review or full accessibility certification is claimed. Earlier local-preview navigation was blocked by browser security, so this revision was checked using a DOM environment rather than an alternative browser workaround. Responsive CSS, contrast tokens and accessible controls are specified; production still requires real browser layout, keyboard, screen-reader and cross-device acceptance tests.

## 25. Requirement coverage and implementation completeness

The separate `Requirement_Coverage.md` maps the original request and blueprint to the exact revised destination, visible behavior and production acceptance evidence. Treat this map and sections 1–24 as one acceptance contract. A feature described in prose but absent from its required screen is incomplete. A visible mock control without its server-side business rule is also incomplete.

The original governance blueprint remains authoritative for commercial policy and operating controls. This UI revision adds no unilateral change to the US35%/India50% policy, CEO authority, legal requirements or release process. Routine display preferences remain separate from governed policy changes.
