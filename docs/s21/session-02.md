# S21F-02 Execution Record

## Three-Hour Handoff (04:26 UTC)

Applicationcheckpointff1be64; full handoff refreshed in handoff.md. Backend at
f944daa:1337passed0failed1opt-in-live skip150inheritedxfails,430.73s, captured
full-financial.xml. Later firstCRM a771a37 and siblingdeletionff1be64 focused
proof10each; not included in that full count. Web latest297pass1failure
(oldnavexpectation);14focusedpasses fixnav and full rerun nowrunning.
Actuals QA b859ead/f944daa four reproduced failures allfixedunchanged; real
PG race additionallyfound uncaughtuniqueconflict, fixedsourceidentitylock.

SoleworkerCRM remainsactive in separatebranch/worktree, now authorized to add
trusted fixture scope using existingsharedreadhelpers withinownedpipelinefiles.
Lead next0052deletionretention; no migration yet. All51IDs/45scenarios retained,
no wholerowclosed. NoS21deployment/mainmerge/inframutation. Save boundary commit
and continue S21F-03 through07:26:53UTC without acknowledgment. External gates
unchanged; complete scope and review controls retained.

## 04:10 UTC Durable Checkpoint (Work Continues)

Reports worker27b46d4 integrated2b9ebbe fixes five previous full-web failures,
including mislabeled GP as revenue; focused Reports9passed. Forecast chart
worker ead499e integrated43cbb8c after real browser reproduced zero-height bars.
Unchanged geometry assertion now passes; desktop screenshot inspected, six
nonzero bars visible. Sticky header artifact resolved by capturing from top.
Local auth groups remain empty in shell; real Cognito navigation still unproved.

Financial actuals0051 applied only to own journey DB; migration parity3passed.
Actuals projection keeps four bases separate, exact FX and exclusion reasons,
Finance/SystemAdmin permission, no addition to service schedules. New test first
failed missing module; source-count and actuals integration assertions reproduced
two defects, then combined40passed. UI test red before implementation, now11pass;
tsc passes. Real HTTP/PG/separate-worker financial journey passed: account
2f71f0eb-2b97-43e3-9739-65e5ce1ad2d3, runfb72397509a2472fb752050d5eb4773c,
four current measures and five retained revisions, unchanged140000/70000 future.
No mocked responses; local identity remains explicit. Evidence
forecast-financial-http-worker.log. Full web running with one worker.

Sole active worker is independent actuals QA on s21/qa-actuals at83ee512,
separate worktree and SQLite runtime. Other development workers idle.
No whole requirement closed, no S21 deployment/main merge. Terraform drift,
old deployed workers, SES readiness and S20 final main-image proof remain open.

## 03:55 UTC Pre-Migration Checkpoint

Forecast UI13a1469 integratedff6ad5b; lead registered /forecast and role-aware
navigation. Source names/calculation versions/assumptions/evidence are now supplied
by authoritative API rows (ae7a837), not inferred from a newer plan. Real browser
integration next after API restart. First full frontend result:279passed5failed,
all failures in existing Reports tests. Sole worker is resolving fixture/default
tab drift plus a real GP-as-revenue labeling bug; no assertions waived.

Financial actuals contract committedc1e435c before code. Additive0051 reserved
after0050: managed batch history, immutable source revisions, exact money/basis,
corrections, trusted/tenant scope, Finance endpoints and detach-on-delete FK.
No invented vendor or live connection. Legacy importer remains separate and is
not relabeled recognized revenue. Initial new tests failed missing model; latest
new8+legacy8passed; final endpoint case running. Migration not yet applied.
All whole requirements remain missing/blocked; no deployment/main merge.

## 03:42 UTC Durable Checkpoint (Work Continues)

Application through ee4659c: Forecast persistence0050 applied only to own
s21_journey; scratch-PG full migration parity3passed. Independent plan QA
bdb5f6c integrated65fa260 exposed8failures; unchanged assertions now pass after
ee4659c fixes. Combined Forecast/isolation80passed. Real HTTP to PostgreSQL to
separate worker process to HTTP passed with independent CompanyX196000/98000,
then persisted probability revision140000/70000; replay0jobs, two immutable
versions/schedules,15month horizon. Evidence forecast-real-http-worker-3.log.
Earlier failures retained: missing fixture-admin JIT (fixed) and an API startup
race (runner launched before listening; readiness verified before third run).

Full backend at ee4659c:1297passed,0failed,1opt-in-live skip,150inherited xfails,
389.57s. Subsequent source-metadata and consumer-health changes have27focused
passes, not included in that full count. Full frontend regression running with
one worker. Fresh unsigned commercial browser1passed19.9s desktop/mobile; initial
signed-basis bug screenshots retained separately, not presented as fixed proof.

Sole worker now D frontend on s21/forecast-ui at65fa260, isolated worktree;
company/account and revenue views only in this increment, three other views and
many lifecycle/actuals/People/automation requirements remain. Lead handles source
metadata enrichment and operations. Full scope not complete or staging verified.

Terraform validation passes; revised whole-root draft8import42add19change7destroy
(task definitions only), no SES identity replacement. Explicit image/account
guard, paired continuous/scheduled switch, topic wiring and healthy-poll metric
prepared. No apply/import, no mail sent. Draft uses old S20 image for inspection
only, MUST NOT apply; candidate image/full drift/real health proof still needed.
No main merge or staging deployment. Continue within04:26:53UTC window boundary.

## 03:21 UTC Pre-Migration Checkpoint (Work Continues)

Projection worker f2a88ed integrated as 1c5eca3: all 31 unchanged independent
Forecast QA tests plus 15 projection tests pass. Exact rational intermediate
scope arithmetic, economic source deduplication, provenance and aggregation
precision replace the nine reproduced failures. No acceptance assertion changed.

Lead adds migration0050 for immutable plan versions, frozen schedules,
transactional retryable calculation jobs and scope conversions. New persistence,
permission/redaction, stale-write, tenant/owner and real malformed-storage fault
tests:5passed. The malformed-storage test is a fault injection, not acceptance
evidence or a mock calculation. Initial fault candidates returned legitimate
reviewable incomplete schedules; the test now injects malformed typed costs.
Migration has NOT yet been applied; only own local databases are next.

Browser commercial edit revealed a signed-basis gap: a new GM could sit beside
an existing released package. Server now rejects in-place signed financial
revision, requiring a separate amendment SOW version; UI read-only guard and
9editor tests pass. The initial browser screenshots are bug evidence, not fixed
acceptance. Fresh unsigned browser proof remains next. Full amendment workflow
still open. Prior full backend1229pass/1live-skip/150inherited-xfail predates this
slice and must rerun. No staging deployment, main merge or infrastructure mutation.

User-authorized window 2026-10-02 01:26:53-04:26:53 UTC; subsequent windows
continue when runtime permits. Scope override committed b92cbe8 in CLAUDE.md
and D-S21F-02. Initial clean HEAD exactly eb04347; existing main and dirty
worktrees preserved. One worker remains the capacity limit: host has 16 GiB,
approximately 150 MiB free pages, substantial compression/swap and 20 GiB
disk free. No evidence supports another heavy concurrent runtime.

## Extraction Investigation

Hypothesis: manual_required is a provider schema failure, not missing IAM
access or worker execution. Read-only CloudWatch /officeapp/dev/api at
1790898588794 corroborates the exact failed smoke: `extract failed schema
validation: payload.fields must be a dict`; next request binds job
9c68a34a-65e9-4466-8923-0b7d6a4e6edc. Existing code used forced tool selection
without strict grammar and mistakenly described this as schema enforcement.

Current [AWS structured-output documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html)
supports strict tools on bedrock-runtime, with a restricted schema subset.
Live synthetic-document probes showed: old schema rejected for open objects;
closed wide schema rejected for nullable enums, then union-count/grammar-size
limits. These were distinct schema revisions, not retries to make one test green.
All failure logs retained. Compact typed named entries plus separate normalized
enums/direct-cost entry passed a real Sonnet 4.6 invocation. Canonical persisted
field mapping remains unchanged; duplicate names, missing fields, malformed
envelopes and invalid locators fail closed without coercion or retry. Output
remains unconfirmed/disputed; schema validity is not factual accuracy.

Regression first: six failed / twenty passed. Final affected extraction,
legacy GM properties and independent checks: 70 passed, no skips/xfails.
Live proof: evidence/baseline/extract-strict-live-typed.log. This is NOT the
deployed upload smoke; staging remains red until candidate deployment and proof.

## Combined Regression

Full combined initial run with disposable Postgres enabled: 1057 passed,
one failed, one skipped (opt-in live Bedrock guard), 150 inherited xfailed.
Failure was QA Oracle B affected by test_gm_properties setting global Decimal
precision 50 at import. Scoped that setting to an autouse localcontext fixture;
unchanged independent oracle assertions now pass. No existing skeleton xfail
is counted as acceptance. Full rerun required after further integration.

## Commercial Lane

Worker 44a3396 integrated as 49b96a3: seven-profile registry, fixed-assignment
fee allocation, confirmed cost-plan inputs and existing-GM adapter. Only fixed
assignment calculator enabled in that checkpoint; other models remain explicit
unsupported drafts. Combined calendar/commercial/independent tests: 58 passed.
Same worker continues remaining calculators in small tested increments.

## Deployment Mismatch

Runbook falsely claims EventBridge targets follow latest family revision.
Actual targets pin revisions 5 (four scheduled workers) and 3 (HubSpot pair).
Registering a newer family alone does not alter those targets. Terraform
scheduler resources already bind exact task-definition ARNs; the historical
CLI registration path bypasses them and conflicts with rule 12. No cloud
mutation performed. Root plan 52 add/13 change/8 destroy remains NOT reviewable
for approval until unrelated drift is reconciled. Corrected deploy must update
and inspect actual target ARNs, not merely describe the latest family.

## Isolated Journey Preparation

Local MinIO pulls from Docker Hub and Quay failed registry access; no container
was created. Existing real SOW bucket has no Object Lock configuration. A local
journey can use actual S3 only with recorded run-owned keys/IDs and explicit
teardown; never enumerate/delete business objects. PostgreSQL remains owned
local state. No feature response or approved state will be mocked or seeded.

All 51 requirements / 45 scenarios remain tracked; these increments do not
close whole requirements. No staging deployment or main merge. Continue without
ordinary checkpoint acknowledgment.

## 01:56 UTC Durable Checkpoint (Work Continues)

Commercial checkpoint 83950f6 integrated as d01e807 (milestone, unit, T&M);
lead combined check 68 passed. Checkpoint 69542fb integrated as cc52930
(calendar staffing and recurring MSP), awaiting lead combined rerun. Same
worker continues hybrid and typed MSP usage; no second worker activated.

Real isolated HTTP journey passed in evidence/baseline/real-journey-2.log:
local migrated PostgreSQL s21_journey, actual S3 and Sonnet extraction,
field confirmation, priced assessment, submission, four existing function
approvals, signed-file verification, delivery acceptance/release, project,
forecast and notification worker (16 rows handled). All run-owned S3 versions
removed. Local identity and external mail sink are explicit boundaries;
synthetic manual signatures are NOT provider-signing/Cognito/SES/staging proof.
The first run failed on runner metadata handling; retained its failure and
corrected it to confirm exactly EXTRACTED_FIELDS. No feature assertions weakened.

This uncovered a genuine signature integration defect: verify endpoint never
downloaded the stored object; service passed bytes instead of DocumentText.
New tests first failed twice. Fixed recorded-key download, SHA256 binding and
real parser invocation: 15 passed, five inherited skeleton xfails (not accepted).
The full path passed with that fix; failed hashes remain blocked.

Next: combined regression, mandatory Sales/governance, versioned persistence
and Forecast consumers; keep infrastructure drift and SES readiness separate.
No deployment/main merge, no whole requirement marked complete. Window still
ends 04:26:53 UTC; this is an ordinary checkpoint, not a stop or approval request.

## 02:12 UTC Pre-Migration Checkpoint

Integrated final commercial worker 2862285 as 518eb12; independent QA now owns
the sole worker slot. QA already reproduced ordinary recurring-fee precision
and hybrid revenue-source duplication defects; remain open pending tests/fix.
All seven calculator names supported is NOT all-model acceptance.

Sales vertical slice: new frozen routing_policy_version=2 requires Delivery,
HR and Sales before Finance/Legal, then conditional CEO. Existing packages
retain policy 1. Preview preserves routing gaps; all submission entry points
reject missing reviewers before creating a package. Required functions are
returned to readiness/signature/review cards; assignment projections use the
same trusted fixture scope as decision authorization. D-S21F-03 records it.
Focused governance regression: 31 passed. UI readiness/marks: see sales-web-final.log.
New migration 0048 follows single 0047 head, additive policy field plus expanded
function constraints; downgrade refuses removal when policy-2 data exists.
Local migration/journey/full regression pending at this checkpoint. Existing
test setup changes seed eligible assigned reviewers and supply review reasons;
second-person decisions are strictly forbidden, repeated assigned decisions
still conflict. No server permission bypass or fixture auto-approval added.

Sales migration completed on own s21_journey database. Real journey rerun at
7b0ec21 passed all five reviews (including reviewer can_decide projection),
signature, delivery, Forecast and worker: 18 rows handled, 13 mail-sink messages;
all S3 versions removed. evidence/baseline/real-journey-sales.log. No staging claim.
Full suite at that revision: 1119 passed, ten failed, one opt-in live skip,
150 inherited xfails. Ten failures were old four-function/concurrency roster
expectations and signed-gate fixtures passing no document bytes. Updated
fixtures/assertions to exercise five reviews and hash-bound real parsing;
focused real-PG and affected regression now 32 passed. Another full run remains
required; independent QA's six new commercial failures are tracked separately.

## 02:29 UTC Durable Checkpoint (Work Continues)

Independent QA 2f7e494 integrated as 22ae7dd: 31 new tests, six reproduced
failures. Commercial worker now owns sole active slot fixing unchanged QA.
First fixes 87b085d/16b0583 integrated as faa797d/178f93f: cross-child revenue
source reuse and calendar precision loss. Ratio-aggregation fix f1f689 integrated
as e37bd6b; worker reports 181 passed, including all 31 unchanged independent QA
tests, with no skips/xfails. Lead combined rerun remains required. Same worker
now builds the pure adapter into the existing GM response contract.

Real local browser proof: one Playwright test passed, no API response mocks,
desktop/mobile screenshots inspected, Sales and HR visible after refresh, no
horizontal page overflow. App http://127.0.0.1:5210; API 127.0.0.1:8210, own
s21_journey DB. Explicit local identity only. Servers remain active for further
integration. Test isolated under tests/e2e/local with playwright.s21-local.config.ts,
not silently included/skipped in staging acceptance. Exact run:
`S21_JOURNEY_DEAL=954a0a67-7747-4bb3-b655-f2129c29f74d npx playwright test -c playwright.s21-local.config.ts`
from tests/e2e. Original proof log sales-browser.log; no staging claim.

Terraform draft imports and real target-version guard committed in 15c616f.
No apply, email send, main merge or S21 deployment. Next commercial persistence
and existing GM-consumer adapter, remaining governance/CRM/Forecast lanes,
combined regression. All requirement/scenario identifiers preserved.

## 02:43 UTC Pre-Migration Checkpoint

Pure adapter integrated as 288f60a. Independent QA follow-up 7778691 integrated
as 2e5ede6: original31 pass unchanged, nine consumer defects plus one new
large-value ratio precision defect. Lead fixes consumer nulls/child floors in
shared policy, Builder and sandbox; commercial worker owns the remaining
precision guard. ONE worker only. Company X artifact has 18 independent
expectation cases, not executed Forecast acceptance.

Commercial persistence slice reserves migration0049 (single head confirmed).
Added typed source/policy binding, immutable snapshot/approval hashing,
optimistic writes and read redaction. New tests first failed missing module,
then reproduced zero weekly cost and read-time recalculation. Focused latest
selection:71 passed, one remaining QA precision failure assigned to worker.
Separate legacy consumers/Sales:41 passed; persistence+weeklyForecast:17 passed
before adding frozen-read test. No weakening of financial expectations; an
initial string-format assumption was corrected to existing exact-string API.
Migration has not yet run against local PG at this checkpoint. Browser editor,
domain event publication and full v3 Forecast still pending. No staging deploy,
Terraform mutation, email send or main merge.

## 02:56 UTC Durable Checkpoint (Work Continues)

HEADac47883 includes projection contract/engine and real commercial journey
runner; QA extreme ratio guardfad62b3 integrated as2383d0b. Lead fixed all nine
QA consumer failures without changing QA assertions. Full combined backend at
2383d0b:1229 passed,0failed,1opt-in live skip,150inherited xfails,333.33s.
Migration0049 applied only to local s21_journey; isolated PG migration parity
3passed. Pure production Forecast projection11passed against independent
CompanyX expectations; this does not close Forecast API/UI acceptance.

Actual PG/S3/Bedrock commercial journey passed: run27fa1d14312341769caa7fb3811b9bf7,
deal86e7c9b5-e6a6-4352-b57b-310c6a997505, package5942d88d-5713-4022-8c03-a7ddb355f930,
forecast224829c5-fe11-43dc-8d19-f0536b9440fe. Five reviews, signed object verification,
delivery/project, revenue24000/cost10000,18worker rows,13mail-sink messages; exact
run-owned S3 versions removed. Local identity/mail boundaries remain explicit.

One worker now B frontend in separate s21/governance tree. Lead next0050
planning versions/schedules/transactional jobs and authorized outlook. All51IDs
and45scenarios retained; whole rows stay missing/blocked. Terraform/import draft,
worker version mismatch, SES sandbox/real recipients and S20 main-image proof
remain unresolved. No S21 deployment or main merge. Window ends04:26:53UTC;
continue without acknowledgment. Effort estimate remains70-100engineeringhours
plus external waits; successful thin-path proof does not remove broad scope.
