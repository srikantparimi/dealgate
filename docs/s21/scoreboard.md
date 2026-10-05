# S21 / Forecast Scoreboard

Current reconciled buckets and per-ID evidence: [progress-20261002.md](progress-20261002.md).
0 completed,49 in progress,2 to do =51; whole-requirement verified completion0%.
Implementation1complete/48partial/2notstarted; verification buckets above are separate.
Acceptance9passed(local)/0failed/28pending/8blocked=45. Historical
`missing` labels below mean not fully proved, not absent implementation.
Current handoff: [claude-handoff.md](claude-handoff.md). Latest estimate33-58
active elapsed hours /37-66aggregate; older ETA text below is historical.

S21F-06 resumed15:14:50UTC after worker quota interruption; lead owns FC-07/10,
FC-09 extraction safeguards and shared regression. No51-ID/45-scenario scope
removed. Coverage archived-source recovery1eff2e8/da6ca77 and actualPGlocks81278e1
are now locally proved; the earlier recovery-QA dependency below is resolved.
Fullbackend0059=2191passed/1inheritedskip/150inheritedxfail; fullweb415passed.
Neither proves subsequent0060/0061 combined regression or staging readiness.

S21F-05 begins 2026-10-02 10:26:53 UTC at ebd6583. Attempting S21-09/10/12,
CO-08, FC-01/07 and CO-02; current states retained pending attributable proof.

51 required IDs; 45 unique S21F acceptance scenarios, with additional regression tests expected. Historical S20 totals are separate in [carryover](s20-carryover.md). No row is verified from a merge alone.

States: `missing` = not yet fully implemented/proved against v3; `fixed and tested` = attributable local/integration evidence only; `verified working (staging)` = matching deployed revisions and business proof; `blocked` = named external prerequisite; `deferred` = only explicit owner-authorized deferral (none).

Every row links [acceptance](acceptance.md); all rows initially have code/local/integration/deploy/acceptance evidence = not_run unless recorded in baseline. Titles summarize, never replace the full contract. Implementation commits must list IDs and evidence paths.

| Requirement | Outcome | Owner | Scenarios | State | Evidence / dependency |
| --- | --- | --- | --- | --- | --- |
| S21-01 | Permanent SOW deletion | B | S21F:T01, S21F:T28, S21F:T32, S21F:T45 | missing | S21F-03:0052/0053retention,fences,parent202/status/retry,8106641QAfixes; real parent browser/PG/worker/S3 run1925e81f passes. All-stage, late-worker/key-race and staging proof remain. |
| S21-02 | Staffing and GM workspace | B | S21F:T02, S21F:T17, S21F:T26 | missing | Unverified v3 scope; assigned in ownership.md |
| S21-03 | Revisitable intake and immutable revisions | B | S21F:T03, S21F:T28 | missing | Unverified v3 scope; assigned in ownership.md |
| S21-04 | Truthful overview | B | S21F:T04, S21F:T10 | missing | Unverified v3 scope; assigned in ownership.md |
| S21-05 | Pre-submit reviewer preview | B | S21F:T05, S21F:T32 | missing | Partial; T05 browser89032/a5ee76d direct preview/edit/submit and exact PG assignments/tasks, hostile IDs rejected. Acting/routing/CEO matrices and deployed roster/OOO/click-through remain. |
| S21-06 | Real reviewers, mandatory HR/Sales and dated OOO | B | S21F:T06, S21F:T35 | missing | Mandatory Sales+HR and frozen historical routing locally proved7b0ec21; dated OOO and real roster remain. |
| S21-07 | Trusted test isolation and contamination repair | B | S21F:T07, S21F:T32, S21F:T35 | missing | S21F-01: partial containment through bd22cb7, 130 affected tests pass; independent 13/13 recheck. Remediation and staging proof remain; implementation-log.md. |
| S21-08 | Approval mail delivery | B | S21F:T08, S21F:T34 | missing | Unverified v3 scope; assigned in ownership.md |
| S21-09 | One filtered population | A | S21F:T09, S21F:T31, S21F:T39, S21F:T40 | missing | S21F-02 firstCRMa771a37 exact client membership and summary joins10focusedpasses; readiness/group/permissions/BUadapter/browser/staging remain. |
| S21-10 | Company and deal ownership | A | S21F:T10, S21F:T27 | missing | 0054sourcefacts,4ecbd6d/83f8bc7authoritativeowner/BUadapter59workerpasses, staleORMcachefence. Sourceownerreaders/facets/UI/local-assignee separation andconnectedstaging remain. |
| S21-11 | Visible persistent filters | A | S21F:T09, S21F:T26, S21F:T31 | missing | Unverified v3 scope; assigned in ownership.md |
| S21-12 | Names and source facts | A | S21F:T10, S21F:T44 | missing | Unverified v3 scope; assigned in ownership.md |
| S21-13 | Deal actions/comments and CRM notes | A | S21F:T11, S21F:T32 | missing | Unverified v3 scope; assigned in ownership.md |
| S21-14 | Persistent per-user alerts | A | S21F:T12, S21F:T39 | missing | Unverified v3 scope; assigned in ownership.md |
| S21-15 | Calendar staffing and economics | C | S21F:T13, S21F:T21 | missing | Calendar/commercial engine, independent oracles and immutable GM storage47119a9; UI calendar configuration/all-profile staging journeys remain. |
| S21-16 | Extensions and nonrenewal | B | S21F:T14, S21F:T20, S21F:T30 | missing | 8857936signedrelease nowuses2calendar-monthrenewalhelper;5literalrelease assertions red->green, combined54pass13inheritedxfail. Amendment/short-engagement/extension/nonrenewal/scheduler/staging remain. |
| S21-17 | Pricing component registry | C | S21F:T13, S21F:T15, S21F:T16, S21F:T21 | missing | Seven typed calculators, QA precision fixes through2383d0b, stored policy/calculation snapshot47119a9; all-model editors/extraction/lifecycle/staging remain. |
| S21-18 | All model intake and legacy migration | C | S21F:T15, S21F:T16, S21F:T29 | missing | Unverified v3 scope; assigned in ownership.md |
| DG-01 | Rule groups and manual watchlists | A | S21F:T12, S21F:T39 | missing | Unverified v3 scope; assigned in ownership.md |
| DG-02 | Consistent client summaries | A | S21F:T10, S21F:T17 | missing | Unverified v3 scope; assigned in ownership.md |
| DG-03 | Navigation context | A | S21F:T09, S21F:T17, S21F:T26 | missing | Unverified v3 scope; assigned in ownership.md |
| DG-04 | Deals are not empty SOWs | B | S21F:T17, S21F:T28 | missing | Unverified v3 scope; assigned in ownership.md |
| DG-05 | Client agreement documents | B | S21F:T01, S21F:T17 | missing | Unverified v3 scope; assigned in ownership.md |
| DG-06 | Continuous governed workspace | B | S21F:T02, S21F:T03, S21F:T17, S21F:T41 | missing | Unverified v3 scope; assigned in ownership.md |
| FC-01 | Five persisted Forecast views | D | S21F:T18, S21F:T26 | missing | Overview2d9fc16/d3e4fa0 plus Company&accounts/Revenue connected browsera1354ea; NextOpportunities351ed9b connected worker proof. ResourceDemandccc539b connected source/publication/People; strengthened S21F-05 financial224000/115584 and seven heads. Generation, retained sources, full permissions and staging remain. |
| FC-02 | Company quarterly outlook | D | S21F:T18, S21F:T19, S21F:T21 | missing | S21F-02 persisted API/workerCompanyX196000 to140000, independent exact expectations; two-view browser and chart fix43cbb8c. Six-account preview and staging remain. |
| FC-03 | Account outlook | D | S21F:T18, S21F:T19 | missing | S21F-02 account drilldown,15months,source evidence and scoped CSV browsere8eeb9e; full preview populations and staging remain. |
| FC-04 | Monthly SOW schedules | D | S21F:T18, S21F:T19, S21F:T21 | missing | Unverified v3 scope; assigned in ownership.md |
| FC-05 | Scenario economics and dedupe | D | S21F:T19, S21F:T20, S21F:T21 | missing | S21F-02 immutable plans0050 and conversion guardsdd4ac6d/ee4659c, independent QA unchanged; real partial-conversion/amendment/event/staging journeys remain. |
| FC-06 | Financial actuals | D | S21F:T21, S21F:T41 | missing | S21F-02 partial0051/e8eeb9e/f944daa: managed four-basis import/corrections, PG exact Numeric and concurrent retained-source proof, real HTTP/browser; matched same-basis replacement/import UI and complete deletion remain. |
| FC-07 | People supply and demand | D | S21F:T22, S21F:T23 | missing | Managedsupplyb6798af and demandccc539b connected proof;0057realPG, global-before-filter7f98459. 0058rules/drafts1c2068b/f709de5/03c1426 PGlocks/history. SourcingQA6reds fixed4600580; connected UI/PG/worker seven heads/two revisions/literal deadlines. Retained source7569d68/681835e realPG and browser survive SOW/client deletion. Coverage d21eb08/3d83bc9/844a6a8:50affected tests,3realPG oracles;12:57 browser4->2->4/history[2,1],9UItests. Independent archived-source recovery QA, full conversion journey, automatic events and staging remain. |
| FC-08 | Growth to CRM pipeline | D | S21F:T20, S21F:T23 | missing | Unverified v3 scope; assigned in ownership.md |
| FC-09 | Evidence and exceptions | D | S21F:T16, S21F:T24 | missing | Audit0dd0432 identifies override/OCR/corpus gaps. Replay48f47f4 preserves confirmed source-bound fields; mutation57f7269 closes immutable/cached-write defects. Lead60tests pass60.60s after worker14+7reds. Conflict review UI, attempt history, primary OCR path, held-out seven-profile evidence and staged live evaluation remain. |
| FC-10 | Safe persistent automation | D | S21F:T24, S21F:T28 | missing | Partial sourcing domain28a7a28/a570334/02fe890: scoped opt-in rules, source event outbox, current authority, atomic publication/draft, persisted status/bounded retry.77affected tests; actual privatePG separateworker/midINSERTkill/recovery preserves7heads andtwohistoryrevisions/auditchain. UI f8aee1e15tests/tsc; connectedbrowser pending. Other automation domains, notifications, source-event coverage/fault/load breadth and staging remain. |
| FC-11 | Scoped exports and snapshots | D | S21F:T25, S21F:T32 | missing | Unverified v3 scope; assigned in ownership.md |
| FC-12 | Reliable recomputation | D | S21F:T25, S21F:T27, S21F:T28, S21F:T29, S21F:T31, S21F:T32 | missing | S21F-02 immutable schedules and persisted retry/dead jobs0050, real separate worker replay1/0/1; whole domain-event graph/crash/load/staging proof remains. |
| OP-01 | Terraform, consumer and monitoring | Lead | S21F:T33, S21F:T42 | blocked | See operations.md and baseline.md; independent code/tests continue |
| OP-02 | Six-person regional mail readiness | Lead | S21F:T08, S21F:T34 | blocked | See operations.md and baseline.md; independent code/tests continue |
| OP-03 | Liberty review recovery | Lead | S21F:T07, S21F:T35 | missing | Unverified v3 scope; assigned in ownership.md |
| OP-04 | Human HubSpot canary | Lead | S21F:T36, S21F:T42 | blocked | See operations.md and baseline.md; independent code/tests continue |
| OP-05 | SES production access | Lead | S21F:T37 | blocked | See operations.md and baseline.md; independent code/tests continue |
| CO-01 | Released baseline and main-image proof | Lead | S21F:T38 | blocked | See operations.md and baseline.md; independent code/tests continue |
| CO-02 | All S20 rows and regression reconciliation | Lead | S21F:T38 | missing | Fullbackend07c36b8:2033pass/1live-skip/150inheritedxfail,728.95s;full-0058.xml. Fullwebc6395e5:403pass/71files302.49s after nav correction; retainedprojectUI22pass/tsc. No inherited gaps hidden;65S20carryoverrows and whole combined staging journey remain separate. |
| CO-03 | Distinct Watching count | A | S21F:T12, S21F:T39 | missing | Unverified v3 scope; assigned in ownership.md |
| CO-04 | SOW approvals card membership | A | S21F:T40 | missing | Unverified v3 scope; assigned in ownership.md |
| CO-05 | Signed delivery and actuals journey | B | S21F:T17, S21F:T21, S21F:T30, S21F:T41 | missing | Real local PG/S3/Bedrock five-review commercial journey passes through project+forecast; actuals/provider/Cognito/SES/staging proof remain. real-journey-commercial.log. |
| CO-06 | Consumer drift adoption | Lead | S21F:T33, S21F:T36, S21F:T42 | blocked | See operations.md and baseline.md; independent code/tests continue |
| CO-07 | Source metadata and crash recovery | A | S21F:T27, S21F:T28, S21F:T29, S21F:T43 | missing | 0055d596dd9/168b605 PG parity/real lock/rollback/resume/loss guards;1c5b245 atomic pages/explicit archive evidence. Independent QA2761da9 exposed six defects;8bd6da6 fixes pass82, PG proof rerun. Separate-process kill/deployed recovery/global-stage PK cutover remain. |
| CO-08 | Business Unit availability | A | S21F:T10, S21F:T36, S21F:T44 | missing | Discovery/adapter4ecbd6d/83f8bc7; observed readers494ae2e pass11realPGoracles; active facets e11196e/d15dd85 pass38API+5UIworkerchecks. Settings availability/labels and permission-aware provider/HubSpot human canary remain. |
| CO-09 | Trusted cleanup and retained financials | B | S21F:T01, S21F:T28, S21F:T32, S21F:T45 | missing | S21F-03:trustedgrantselector/strictage4c137b8,QA46affectedpass8106641; real parent cleanup retains24680.125/project and removesexactS3versions. Full trusted graph/staging sweep/counts/scheduledworkeractivation remain; disabledbydefault. |
| CO-10 | Historical and combined human acceptance | Lead | S21F:T30, S21F:T36 | blocked | See operations.md and baseline.md; independent code/tests continue |

## Separate Totals

### Tracked Editor And View Subitems

These are work items mapped to existing requirement IDs, NOT extra requirements
or acceptance scenarios. No whole requirement is promoted by these unit results.

| Work Item | Existing Requirements / Scenarios | Current Evidence | Connected Proof Still Required |
| --- | --- | --- | --- |
| ED-01 Hybrid model-change confirmation moves to sibling after removal | S21-17,S21-18,FC-05 / T15,T20 | QA4057138 red;fix5ccabf6,independent40/40;real5c9a7fb removes pending child and preserves unit sibling through save/reload,1250revenue/1000cost | Newly extracted hybrid upload and approval/signature/Forecast |
| ED-02 Unsaved edited preview labelled Saved calculation | S21-04,S21-17,FC-09 / T04,T15,T16 | Same QA/fix;5c9a7fb real preview/edit/save/reload distinguishes stale preview, immutable version | Failure/retry states and all-model approved downstream snapshots |
| ED-03 First calendar assignment unavailable for empty fixed/MSP staffing | S21-15,S21-17,FC-07 / T13,T15,T22 |5c9a7fb real fixed/MSP firstcalendar assignments;2people*0.5allocation*2days*8hours*40=640plus1000directcost persisted | Downstream People fullheadcount/approval/signature/Forecast |
| ED-04 Existing MSP credits/usage lack correction controls | S21-17,S21-18 / T15,T16 |5c9a7fb real correctionssave/reload;independent revenue20000-17+(13-2)*10=20093 | Newly extracted uploaded terms and approved monetary schedule |
| ED-05 Unsupported persisted pricing hides editor without validation | S21-17,S21-18,FC-09 / T15,T16 | Real run cf51a3ea passes visibleunsupported/disabledactions/explicitreplacement/save/reload;original unsupported version retained and evidence unchanged | Explicit unsupported submission rejection and full corrected approval/signature/Forecast journey |
| FV-Overview | FC-01,FC-02,FC-04 / T18,T19,T26 |2d9fc16/d3e4fa0 independent30boundarycasesfixed;realbrowsera1354ea scopes,reloads,exports and matches140000/70000 futurebasis | Persisted expiry/renewal/linkage/resource/concentration gaps; not whole-view acceptance |
| FV-ResourceDemand | FC-01,FC-07 / T18,T22,T23 | Supplyb6798af, demandccc539b connected; browser seven heads remain after70%-40% and Upside switch, future224000/115584, two sourcing revisions with USSept17/IndiaOct2. Retained681835e browser/deletion; coverage3d83bc9/844a6a8 plus12:57 browser4->2->4/history. Desktop/mobile screenshots reviewed | Archived-source recovery QA, automatic source events, complete match snapshots and staging remain |
| FV-NextOpportunities | FC-01,FC-08,FC-09,FC-10 / T18,T20,T24 | ff8d10f/351ed9b integrated fourth view; 34 API and 22 UI tests. Connected browser edits assumptions/probability, version3 + separate worker, future168000/84000, actual11000.99 unchanged; desktop/mobile proof. | Automated opportunity generation, true source link/local-only distinction, source-change and signed conversion journeys, full permissions/staging remain |

### Release Gates

| Gate | Meaning | Current State |
| --- | --- | --- |
| Engineering-ready staging | Complete feature candidate on attributable staging frontend/API/worker/schema revisions; combined technical and business-flow tests pass | NOT READY: implementation/connected proof and deployment remain |
| Operationally verified staging | Engineering gate plus approved infrastructure convergence, real consumer/alarm/recovery/canary and required mail readiness/provider evidence | NOT VERIFIED: operational dependencies remain |
| Product-owner acceptance | User completes requested staging click-through and explicitly approves merge | NOT REQUESTED; no inferred acceptance |
| Deployed main | Approved merge, resulting main-image deployment and final smoke/business checks verified | NOT STARTED; no S21mainmerge |

Latest remaining estimate: [44-74aggregate agent-hours /31-49active elapsed hours](remaining-estimate.md)
held at10:56UTC, external waiting separately unbounded. This updates the earlier forecast and supersedes historical
70-100hour notes below without erasing their checkpoint context.

| Lane | Required | Missing | Blocked | Fixed and tested | Verified staging | Deferred |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S21 | 18 | 18 | 0 | 0 | 0 | 0 |
| DG | 6 | 6 | 0 | 0 | 0 | 0 |
| FC | 12 | 12 | 0 | 0 | 0 | 0 |
| OP | 5 | 1 | 4 | 0 | 0 | 0 |
| CO | 10 | 7 | 3 | 0 | 0 | 0 |

Requirement coverage: 51/51 mapped. Scenario definitions: 45/45 mapped; execution is NOT 45 passes. Existing S20 checks retain their own counts. Initial baseline smoke: one run, failed extraction; cleanup gate reported zero with known limitations.

Final S21F-01 checkpoint: no whole requirement promoted from a partial local increment. Five real PostgreSQL checks pass separately. No S21 staging deployment or merge; final-main-image proof still blocked by observed deployment mismatch and red smoke. All 51 IDs remain listed in exactly one state. Revised full effort 70-100 engineering hours plus external waits; exact resume and ownership in handoff.md. S20 historical rows remain separately reconciled, not silently reclassified.
