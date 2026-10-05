# Business Demonstration: 2026-10-03 03:17 UTC

Evidence-based snapshot, not a new broad test run. Latest focused-tested application
44fec5163c722e87eaeb69f0c486ce32a875d4c0; latest closed connected workflow
T19 financial preview/edit/reload. Independent QA's remaining assertions now
pass93529. Twelve of45 scenarios passed locally;25pending/8blocked.
S21 has **not been deployed**.
The observed staging site still runs S20; neither its merged source nor older
smoke establishes the S21 outcomes below.

| Workflow | What a user can do now (local evidence) | Exact next missing or unverified step |
| --- | --- | --- |
| Preview financial planning (T19) | Twelve real persisted sources across six accounts match independent15month/fivequarter/three-scenario revenue and cost literals. Edit follow-on service/allocation/cost dates, fixed fee and probability; separate workers calculate each revision, reload and reconcile account/company and affected views. Browser54224 plus93529 pass; original version remains and old-period contribution is removed. | T19 closed locally; wider profile/conversion and staging gates remain separate. [Evidence](lanes/t19-plan-terms.md). |
| Five Forecast views (T18) | All six original conditions pass locally. Navigate five persisted views, retain scope/period/scenario, export CSV, edit assumptions, publish staffing, save/clear coverage and page history/sources. Exact nonempty coverage intervals pass69292; source link/Back8316 closes the last defect. | Parent FC-01 renewal/linkage and broader permission behavior remain; staging is unverified. T18 local closure is not parent completion. |
| People source updates (T23) | After API-authored start/headcount change, visibly republish stale demand and prepare a new sourcing draft; old lines/history preserved. Sales-only sees exact owned demand without costs/names; planning cannot reserve/hire.88901/49160 plus44tests74987. | Date/headcount editor itself, broader automatic source-event/financial matrices and liveHR/staging. |
| People capacity (T22) | Publish seven half-time slots, import six-person roster, see exact2.5FTE matched/1FTE gap and regional sourcing deadlines; changing70->40% preserves staffing and draft history.84625/e879213 plus27 current tests cover overlap/roll-off/continuity. | Full signed-amendment/event/lifecycle matrices and operational HR/staging, not a reservation or hiring action. |
| Reviewer planning (T05) | Open Approvals directly, see five eligible reviewer groups, change Delivery and submit; reload preserves exact assignments and three task owners. Invalid IDs, self/duplicate/nonmember selections and unauthorized submission rejected without rows.89032/a5ee76d. | Acting/OOO/routing-reason/CEO matrices, actual business roster and staging. |
| Comments/actions (T11) | Add/edit/pin comments; create/edit/complete dated assigned actions; reload and inspect attributed activity. Concurrent edits preserve exactly one winner; unauthorized edits fail without audit writes. CRM notes visibly read-only.43442/1441649, real PG69943. | Broader unpin/live CRM-note integration and availability, Pipeline latest-comment edit parity, Cognito/staging. |
| Watching | Star a deal shared across three groups; card and list contain exactly that one authorized deal; unstar returns both to zero. T39 all assertions pass46207 at941953a. | Combined staging execution; wider T12 dynamic-rule/filter/alert behavior remains separate. |
| Filtered Pipeline | Select owner/BU/stage; exact64 deals over3pages/16 clients/USD64000, export every matching deal, remove one chip, reload/Back and apply saved views. Delayed genuine old responses cannot replace zero results. T09 passes62013/508c450. | Broader date/multiselect/permissions/mobile/load and staging matrix; real source parity separate. |
| Approval card | Card opens exact in-review SOW packages, not Pipeline; two SOWs/one deal and five reviewers each still count2. Pinned pages and stale-link refresh pass99369/205d51a. | Combined staging verification; broader actual approval lifecycle remains in separate scenarios. |
| Pipeline to signed delivery | Use an authorized Pipeline deal, upload a real SOW, complete five reviews, verify matching signed bytes and accept Delivery into one Project. Connected94568/d25e136. | Complete browser/Cognito/mail path; wrong-version/signatory and lifecycle matrices; all seven pricing models. |
| Delivery to Forecast/actuals | Same-project94568 preserves signed baseline and four distinct bases. T21 now imports Finance-certified half-scope and visibly shows23000.99/11000 estimate, corrects to22500/11000, reloads, preserves original24000/10000 and history; replay and real PG overlap/identity races pass. | Full financial import UI, legacy ActualPeriod reconciliation and wider conversion/source lifecycle cases. T21 starts from an explicitly seeded signed prerequisite; no new signature or staging proof. |
| People to sourcing | Released seven-head demand is processed by separate workers; missing capability requests review, human enrichment yields a Draft sourcing result; replay does not duplicate.94568. | Remaining event domains, full authority/fault/load matrix, production worker deployment and notifications. |
| Commercial editing | Local editor fixes cover first calendar, fixed allocations, recurring adjustments, hybrid terms and unsupported-model replacement; literal economics checked.5c9a7fb/cf51a3ea. | Full seven-profile upload-to-monthly-forecast workflow, missing-input matrices and amendment continuity. |
| Calendar economics | Resolve unknown calendar/cost in the editor; save/reload US60 billable/66 paid and India80/88 hours with exact money and daily holidays. Missing inputs stay unresolved; India45% fails its floor. T13 passes41842/00371d2 plus78 oracle tests. | Calendar registry/configuration, frozen-version presentation, downstream reconciliation and staging. |
| Extraction review | Review a source conflict without overwriting a newer human correction; explicitly supply missing CAD; matching typed signatories pass real provider journey.19949/94568. | Primary OCR, attempt history and held-out scan/ambiguous-document quality. OCR authored red tests are not implementation. |
| SOW workspace | T02 passes37810: Overview/Staffing/Approvals/Back/deep-link/reload preserve same SOW/version, header/tabs and one readiness panel. | Broader keyboard/mobile/context/CTA matrix and matching staging. |
| Deletion | A real parent cleanup removes owned object versions and retains a Project with actuals24680.125.1925e81f. | All six SOW stages, late-worker/callback/key races, all count surfaces and staging sweep. |
| CRM source/recovery | Distinct company/deal owners, metadata/facets and recovery locks have local component/PG evidence; filtered CSV snapshot retains1002 exact rows/2002USD despite concurrent mutation.224f7f7. | Full source-to-UI human canary, deployed consumer, all names/BU permissions and crash recovery. |
| Operational release | Reviewable source changes and controls exist. | Exact-image reviewed Terraform plan/approval, worker alignment, real roster/mail readiness, combined staging evidence, then PO click-through and main approval. |

## Changed Since The Previous Checkpoint

Since T18: monthly staffing cost basis supports explicit salary/allocation without
invented hourly rates or duplicated costs. New plan commercial editor preserves
scenario/FX metadata and canonicalizes first-time Finance authors.64316 API9pass,
71788 UI8pass/typecheck96773; connected54224 passes1/1.7min. Earlier pre-edit
financial matrix25684 proves all12source costs/revenue. No staging or parent closure.

### Previous T18 Checkpoint

Since1339717: backend empty-account repair integratedae753de, frontend context/
period fixes committedfa0c787.26 focused UI tests41393,5 API4816 and typecheck
76705 pass. Connected navigation25161, empty/error67649, assumption/publication
controls99259, coverage/history31702 and source-paging32834 now pass locally.
Independent QA tightened visible-control checks; exact intervals and corrected
async source-anchor navigation now pass69292/8316. T18 closes locally;11 of45
scenarios passed,26pending,8blocked. No deployment or parent completion claim.

### Previous T21 Checkpoint

T21 financial workflow now closes locally at19ca6f7: full browser76926,
PG identity11028 and current/replay/responsive33980. Two actual lock defects
were reproduced and repaired without retries or weaker assertions. Ten local
scenarios now pass; every parent requirement retains its separate status.
No deployment, infrastructure approval or PO acceptance has occurred.

### Historical Checkpoint Changes

Watchlist access/distinct-count changes9f23cb4 and candidate-grant scan repair
941953a now have the complete T39 local pass. CSV snapshot/filter repair224f7f7
has real concurrent PostgreSQL evidence. Condition maps3573130/3109012 expose
completed clauses without hiding parent remainders. T39 evidence checkpoint
39f1575 is committed. T02 workspace proof623a5a8 closes navigation locally.
T40 snapshot repairs205d51a and independent reviewef32dd6 close exact approval
population, pagination, stale-link recovery and later-lane visibility locally.
T13 now also closes locally after bde6d29 exposes saved calendar details and
00371d2 proves visible values and persisted unknown inputs.
T09 closes locally at508c450 after repairs to ordinary-view page size, saved-view
filter/sort restoration and authenticated filtered export; private proof DB cleaned.
No new deployment or operational approval has occurred.
T11 now closes locally at1441649: connected controls, two actual PG concurrency
races, Sales/HR access, stale-draft recovery and separately attributed CRM notes.
Independent QA exposed two route races; both now have red-to-green regressions.

Previously zero complete scenarios reflected a real evidence gap: the long
happy-path journey did not assert every adverse case/matrix in its compound
scenarios, and T39 initially failed readiness. T39 is now the first fully asserted
local scenario, followed by T02, T40, T13, T09 and T11. None implies staging acceptance.
T05 now also passes all four literal conditions locally (89032). Seven local
scenarios are closed; no staging or operational gate has changed. Both isolated
T05 databases were removed after ownership checks; retained journey data untouched.
T22 now closes locally from the mapped combined evidence and connected part-time
proof84625. Eight scenarios closed locally; its private database also cleaned.
T23 now closes locally with strengthened admin/Sales browser evidence and44
permission/privacy regressions. Nine scenarios closed, no operational/staging
promotion. Both private databases cleaned; retained data preserved.

All original [51 requirement rows](progress-20261002.md#all-51-requirements) and
[45 scenarios](acceptance.md) remain intact. [Requirement conditions](requirement-conditions.md)
and [scenario conditions](scenario-conditions.md) distinguish verified local,
implemented-unverified, missing and blocked clauses. Counts are not percentages.
This snapshot does not replace their live ledgers.
