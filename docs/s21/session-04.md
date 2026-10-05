# S21F-04 Execution Record

Authorized window:2026-10-02 07:26:53-10:26:53UTC. Continue under D-S21F-02;
preserve all isolation, Terraform/human approval and no-main-merge controls.

Baseline d596dd9 plus authored scan-lease tests. Last fullbackend28775b2:
1465pass/1opt-in live skip/150inheritedxfails. Latestfullweb remains older306pass,
new70targetedpass; combinedfrontend rerun remains required.

Attempted rows thiswindow: CO-07/08,S21-10/12 (source metadata/scan recovery),
FC-01/07 (People-demand and remaining views), CO-02 (combined coverage gaps).
All retain missing until wholeoutcomes proved. Operations OP-01/02/04/05 and
CO-01/06/10 remain externally gated; continue independent implementation.

Lead owns0055schema/scanprotocol, integration/tests/deployment. WorkerA owns
source adapter in s21/crm-metadata, latest57localpasses pendingcommit. Second
light QA owns only docs/s21/qa-regression-gaps.md in s21/qa-regression-gap;
no runtime. No third worker; heavytestsserialized. Own runtimes Vite5210,
PostgreSQL55421, API8210stopped. Disposable s21_schema only for destructiveparity.

Next: review/integrateA2, real0055rehearsal, transactionallease tests/implementation,
renewal conflict reconciliation, sharedsourcefilters, People schema and views.
Record checkpoints~30minutes and before riskyops; do not wait for acknowledgment.

## 07:56 UTC Checkpoint

IntegratedA2worker1585edc/6447305 as4ecbd6d/83f8bc7,59affectedpasses;
qualifiedstageworker6a64321 as3cba12c,58passes1inheritedxfail. Frozenprovider
metadata validatesprobability ratherthanEnglishlabels, globalIDconflicts refuse
until laterqualifiedPKcutover. Leadcallerqualifiedin1c5b245. SourceUIstillopen.

0055schema d596dd9:6red->6green,3PGfull-chainparitypasses. Leaseprotocol168b605:
9red->9green. RealPGscriptbe4c973 passes legacy-rowupgrade/emptyroundtrip/three
lossrefusals, observedactualDBlockwait, refusedconcurrentowner, atomicrecord+
cursorrollback, samegeneration/cursorresume withnewtoken, stalefailure/completion
refused. Scratchs21_schema0055only, retainedjourney/leadDBs still0054.

Backfill1c5b245:8newcasesallred beforefix; firstcombined56pass1fail exposed
404ownerfallbackregression, fixedwithoutweakeningassertion. Finalaffected103pass
32.80s (before onequalifiedcallerline); nextcombinedrerun afterindependentQA.
Pagefetch/dependencies outsideownedtransaction, records/audits/seen/cursoratomic,
explicitarchivedrecordevidence required, scopebinding explicit. Realclientneeds
HUBSPOT_PORTAL_ID+tenant/env configured; no liveprovider/stagingclaim. Stubclient
now hasexplicitfixturemetadata instead of accidentallyattemptinghttp://stub.
PrimarySDK archived-read evidence:
https://github.com/HubSpot/hubspot-api-python/blob/master/hubspot/crm/deals/api/basic_api.py
No separateprocesskill proof yet;8boundarycases are not45scenarioacceptance.

Independentregression inventoryda4de2d integrated59e737c:150xfailcases across
30files,1opt-inlive skip,11legacybrowserstepsskipped. Actualrelease60daysbug
reproduced5literalassertions; worker30b8bf2 integrated8857936 uses existing
calendarhelper,54affectedpasses13inheritedxfails. Broaderrenewalpaths remain.

QA nowowns scan adversarialnewtests inownbranch; candidates include cursorcycles,
archived-ownerpartialfailure, failedpreleasefreshness andfinalizermappingchange.
D author-only Nextopportunities/assumptionedit inownbranch undera5ef409contract.
Hostpressure again70load/89runnable limits toone heavytestslot. No otherworker,
cloudqueue/mail/deploy/infraapply/mainmerge. Fourreleasegates unchanged.

## 08:20 UTC Checkpoint

HEAD 351ed9b. Independent scan QA 93853c5 integrated as 2761da9; 9 failing
assertions across 6 defects fixed in 8bd6da6. Combined first run 81 passed / 1
failed; legacy restoration fixture now has explicit newer source evidence with
unchanged business assertions. Final 82 passed in 33.12s, no skip/xfail.
PG script rerun after remediation passed actual lock wait, exclusive acquisition,
atomic page rollback/resume, stale-owner refusal and migration loss guards.
Separate-process kill and deployed worker proof remain open.

People pure allocation engine 8eaa237 passes 14 literal headcount/capacity
oracles; schema/API/UI/import/sourcing are not implemented. Independent QA now
authors edge cases in its own tree. Next opportunities fourth view and guarded
immutable assumptions revisions integrated ff8d10f/351ed9b; combined integration
checks and real connected browser journey in progress. Third Overview view
already has bounded connected evidence; fifth Resource demand remains missing.

Capacity recorded in ownership.md: one lightweight worker, heavy tests serialized,
not an account quota restriction. No staging deployment, infra application or
main merge. ETA remains 33-51 active elapsed hours / 46-76 aggregate agent-hours
pending evidence from these integrations; external waiting remains separate and
unbounded. Small pure-engine progress does not retire People delivery-chain work.
All 51 requirements / 45 scenarios and all four release gates remain visible.

## 08:48 UTC Checkpoint

Full web run on integrated Next opportunities plus textarea label fix: **365
passed /67 files in259.33s**; TypeScript passed. Connected Next opportunities
test initially failed due missing local test group (fixture isolation correctly
hid account), then reproduced textarea accessible-label defect. Unchanged
assertion passed after explicit label:1browser test23.8s /28.2s total, desktop
and390px mobile reviewed. Version3 probability0.60 persisted, separate worker
recalculated future168000/84000, actual11000.99 unchanged. PG inspection retained
versions1/2/3 at probabilities0.70/0.50/0.60, alljobsdone. d2024fd checkpoint.

People independent QA35bbe8d:13red across6groups; d44545b fixes +2 further
controls yield46passes. Pure only, no T22/T23 closure. 0056supply9ff08f6:
missing-module red collection ->11storage passes,3PGparity passes8.70s inowned
s21_schema. Managed import foundation now25combinedpasses15.76s after replay
timestamp format fix; initial24pass1fail retained. Server-derived test-source
flag added to0056before deployment, so repeat PGparity is required. HTTP tests
authored, endpoint/UI/Peoplepublication/sourcing still outstanding.

Truthful linked-source worker117728d integrated8d9253f:11/13red ->32combined
passes. Local deal no longer labelled CRM merely because linked. Further
outlook stale-link remediation inworker; browser snapshot above predates label
correction, must renew after integration. Original user checkout untouched.
Remaining forecast32-50active elapsed /45-75aggregate, externalwaiting separate;
no new credit for partial import foundation. No staging/PO/main gate closed.

## 09:18 UTC Checkpoint

Managed supply realbrowser proof:1passed14.6s/19.1stotal, exactallocation
0.123456789012345678901 persisted through upload/reload/correction, twoimmutable
batch revisions/history. PG query confirmed original andcorrected names/source
dates; source synthetic-browser-95d3ab49-8b16-45ce-b190-997f9489dd32. Initial
missingroute and thenexacttextarealabel assertions failed; explicitlabel fixed
withoutweakeningthebrowser. RawbatchUUID replacedbyrevision, uploaderUUIDbyname;
unitCASassertion strengthened tocheck refreshedbatch key. Desktop/mobile reviewed
nonblank/no pageoverflow; tablehorizontal scrolling retained.13integratedUI/nav
passes. Localnav uses tokenroles; Cognito navigation stillrequiresstagingproof.

WorkforceQA4278726:35pass5red. f68661e fixes allunchangedprecision/timestamp
assertions; newExactNumeric uses PostgreSQLNUMERIC andSQLiteexacttext, no
ambientcontext rounding.67combinedimport/API/storage/demand-schema passes.
0057publication0c8880b:10schema cases withinthatselection; PostgreSQLparity
running atcheckpoint. Sourceprojectionworker authoringnewpureadapter; publication
service/global demand/API/UI/sourcing stillopen. 0058remains reserved.

Retaineds21_journey upgraded0057 in place; API8210session5063includes latest
people-name presentation. Vite5210session19788, ownPG55421 unchanged. No shared
data/infra/mail/staging/main change. Remaining31-49activeelapsed /44-74aggregate,
externalwaiting separateunbounded. Engineering-ready staging NOTREADY;
operationalstaging NOTVERIFIED; POacceptance NOTREQUESTED; deployedmainNOTSTARTED.

## 09:46 UTC Publication Checkpoint

eda7300 projection,2f76883 saved-plan staffing binding (16red->73affectedpass),
169ab31 publication/API (37affectedpass),eaa2045 realPG proof integrated.
PG0057 proves28fractional allocation, actual source lock wait, stale writer409,
two immutable revisions/two audits, explicit stale read after source revision,
populated downgrade refusal/head preserved. Renewed0056supply proof also passed.
Independent projectionQA656b0ac produced11reds in63tests;0090261 fixed unchanged
QA and added10edges:162combinedpassed. No wholeT22/T23 claim.

Second lightweight slot now used: resource-demand UI worker and independent
publication QA in separate trees, explicit files. Runtime serialized; QA owns
current bounded slot. Lead authors globalallocation-before-filter tests and
manual-enrichment preservation regression. No new approval request or waiting.
Remaining elapsed31-49 andaggregate44-74held, notdividedbyworker count.

## 10:19 UTC Combined Regression

Full backend at exact application commit7f98459:1849passed,1opt-inlive skip,
150inheritedxfails,62warnings,895.89s; JUnit evidence full-0057.xml. No added
skips/retries/xfails or weakened assertions. This supersedes28775b2 for local
backend regression only, not model-journey/provider/deployment acceptance.
Parity used ONLY disposable s21_schema; retained s21_journey remains0057.
API8210 restarted at7f98459 backend, session4607; Vite5210 retained19788.

10:17read-only deployment refresh remains API70/S20 image, sixold scheduled
workers and missingcontinuousconsumer; binding gate fails7checks withzero
observationerrors. SES remains sandbox200/day1/sec0sent. No AWS mutation.
Frontend parentwiring andCompanyX realbrowser spec authored, notyetexecuted.
Serialized queue: A BUredrun, independentCompanyX8+3cases, leadUI/browser.

## Boundary Handoff

Local parentwiringccc539b:29UItests/tscpass; firstresourcebrowser1pass45s,
53.3stotal, desktop/mobile reviewed. Sourcepublication/People/revision/headcount
proof passes. Screenshot alsoexposes syntheticfixture duplicatecostsources;
correctfixtureIDs andaddindependentfinancial/scenarioassertions nextwindow.
IndependentCompanyXfd1d6ad:11passes; A BUworker29green after12red, commitpending.
No acceptance row becomes verifiedworking(staging). Fullmatrix remains
scoreboard.md; all51IDs and45scenario mappings retained. Fourreleasegatesopen.
Complete current runtime/resume inventory is handoff.md 10:26header.
Continue intoS21F-05 without acknowledgment underauthorizedoverride.
