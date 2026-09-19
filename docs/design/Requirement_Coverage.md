# DealGate V2 — original requirement coverage

This map was checked against the original conversation, the 12-page governance blueprint and the complete UI/UX specification. The first concept left several controls mainly in documentation or secondary tabs. V2 gives them dedicated entry points and connected workflows.

## Critical corrections

| Gap in first concept | V2 correction |
|---|---|
| Agreement status was secondary and most sample clients appeared verified | Pipeline clients now shows separate NDA/MSA columns, with missing, requested, expired and awaiting-signature examples |
| Approvals was chiefly a queue and a few detail cards | SOW approvals is a six-lane lifecycle board with ownership, stage age, agreement state and four functional review markers on each card |
| No connected new-SOW journey | New SOW studio runs source/type → scope/terms → GM → named routing → submission |
| CEO approval was a mostly isolated screen | Below-floor SOWs route from their functional reviews into a version-specific CEO decision, conditions and signature gate |
| Condition text did not visibly control signature | An unverified pre-signature condition blocks signature; recording its evidence changes readiness |
| Signed-SOW distribution was described more than shown | Signed handoff displays recipient, exact package, delivery result, acknowledgement, setup tasks and Delivery acceptance |
| Repeated panel layout felt generic | Command center, approval board, intake studio, decision workspace and renewal timeline use purpose-specific compositions within one visual system |

## Requirement-to-screen contract

| ID | Original requirement | Visible destination and behavior | Production acceptance evidence |
|---|---|---|---|
| R01 | Transparency across Marketing, Sales, Presales, Delivery, HR, Finance, Legal and executives | Command center → priorities, agreement readiness, approval lanes and delivery economics; role queues share source records | Authorized roles reconcile to the same records and financial definitions |
| R02 | Marketing enters functionality before a technical plan exists | AI discovery → Brief & estimate captures client, domain, functionality, budget, model and unknowns | Incomplete briefs create questions; fields preserve client-provided versus inferred information |
| R03 | AI researches the client and public context | AI discovery → Evidence & assumptions separates public research, client facts and assumptions | Verified entity, source URLs/access dates/excerpts; no fabricated results when research fails |
| R04 | Immediate staffing and cost insight, not source of truth | AI discovery shows roles, effort, cost range, confidence and validation handoff | Estimate cannot approve, quote, hire, sign or release; deterministic financial calculations |
| R05 | HubSpot opportunity entry starts ownership and tracking | Pipeline clients and client activity show commercial stage, owner, next action and sync | Idempotent event handling, conflict resolution, missing-owner assignment and reconciliation |
| R06 | Track NDA signing status for pipeline clients | Pipeline clients → NDA badge → agreement Overview / Signature & evidence / Linked work / Activity | Complete lifecycle, correct legal entity, owner, next action, execution evidence and Legal verification |
| R07 | Track MSA signing status for pipeline clients | Separate MSA column and NDA & MSA register; Atlas awaiting-signature example | NDA readiness cannot imply MSA readiness; missing/expired/unsigned coverage holds the required gate |
| R08 | Track progress and next client check-in | Pipeline row and client Overview; Update next client action | Required outcome/action/owner/date, aging and manager escalation; no orphaned follow-ups |
| R09 | Upload new SOW and verify terms | New SOW studio → Source & type / Scope & terms; SOW → Documents | Upload scanning/duplicates, extraction page references, uncertainty flags and verified commercial fields |
| R10 | Automatically prepare an appropriate GM sheet | Studio → Build GM and SOW → Staffing & GM | Model derives from verified SOW plus approved rates/HR/Delivery data; absent cost remains incomplete |
| R11 | Staff augmentation and one consultant | Separate template choices with resource/role/time/rate modeling | Billable versus paid time, loaded cost, leave/utilization, overtime, replacement and term tested |
| R12 | Small projects and 2/4-week assessments | Fixed-price and Assessment templates, deliverables/effort/acceptance fields | Duration does not substitute for effort; prep, workshops, analysis, travel and report review included |
| R13 | T&M and managed-service models | Separate templates with cap/coverage/recurrence semantics | Forecast value separated from cap; coverage, shifts, onboarding and minimum staffing reflected |
| R14 | US minimum35%, India minimum50% | Margin lab, Build GM, package summary and CEO comparison panels | Unrounded tests using Finance-approved delivery cost policy and decimal money arithmetic |
| R15 | Mixed onshore/offshore projects | Build GM shows US/India revenue and cost independently; combined values derived | Finance-approved allocation, no unknown geography/unallocated cost, no blended masking |
| R16 | SOW/GM approval by Finance, HR and Legal | Functional-review lane plus four named cards; Delivery technical baseline shown first | Accountable identity, checklist, evidence, reason, timestamp and exact SOW/GM/policy versions |
| R17 | Sales must not commit to impossible delivery | Delivery scope/effort/capacity gate precedes the functional package | Signature, requisition and release enforce readiness outside the visual UI |
| R18 | Below-margin SOW requires additional CEO approval | CEO exception lane → project case, exact shortfalls, alternatives, downside and conditions | Additional authority only; no waiver of outstanding Legal/HR/Delivery/Finance requirements |
| R19 | Explain the project to the CEO | CEO page contains scope, term/model context, team evidence, revenue/cost/profit, shortfall, rationale and alternatives | Incomplete business explanation blocks final submission; future revenue remains speculative |
| R20 | Signed SOW reaches account owner and leadership | Signed handoff → Distribution lists functions, packages, delivery outcomes and acknowledgements | Verified recipients, role-appropriate data, reliable delivery, retry deduplication, no salary leakage |
| R21 | Document everything | Client/SOW/agreement Activity; immutable versions; Settings → Audit log | Append-only decision history, change diffs, retention, source identity and authorized access |
| R22 | Client GM based on individual SOWs | Client Financials, Delivery & actuals and Reporting | Revenue-weighted rollups with consistent currency, period and approved/forecast/actual basis |
| R23 | Alerts two months before expiry, weekly updates | Renewals → Action required / Weekly follow-ups, timeline and owner actions | Calendar-month arithmetic, timezone/month-end, seven-day repeat, immediate short-engagement review |
| R24 | Look at renewal updates and escalate | Weekly reminder history, outcome validation, notice deadline and 30/14-day milestones | “Discussion ongoing” does not close; final evidence requires verification; failed sends stay visible |
| R25 | Real operational margin visibility | Delivery & actuals → baseline, forecast, actuals, reconciliation, staffing and changes | Cost incurred + cost to complete; incomplete imports/timesheets visible; variance creates recovery |
| R26 | Clear process, expectations and subordinate ownership | Every gate/decision identifies function, person, due date, evidence and next action | Assignment/delegation, aging, escalation and segregation of duties enforced server-side |
| R27 | Reliable integrations and historical work | Settings → Integrations / Data imports / System health / Audit | Safe retries, no duplicated side effects, legacy evidence gaps explicit, signed history retained |
| R28 | Modern and appealing experience | Editorial executive banner, violet controls, warm neutral surfaces, lifecycle cards, context side panels and responsive compositions | Human review of actual browser screenshots, real data density, readability and accessibility |

## Prototype versus production

The revised concept contains connected local demonstrations of the most important workflow paths. Ten non-browser interaction test groups passed. It does not contain real HubSpot credentials, identity enforcement, live public research, document extraction, durable workflow workers, financial posting or outgoing messaging. Those are explicitly required production services, not implied by the visual controls.

Seeded historical approvals and distribution receipts are labeled sample data. The new-SOW studio can submit and advance a local sample package, but these actions carry no external authority. Secondary editing forms illustrate layout and interaction contracts. Browser screenshot and assistive-technology verification remain outstanding; no visual certification is claimed.

## Completion rule for the coding agent

For each R01–R28 requirement, report four things separately: screen implemented, server behavior implemented, integration configured, and user journey verified. A screen alone cannot satisfy a business control. A prose description cannot satisfy a visible UI requirement. Record blockers, evidence and the owner of any remaining work.
