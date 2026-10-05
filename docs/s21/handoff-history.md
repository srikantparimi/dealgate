# Handoff History

## Connected Attempts Before 1932757

41076 ondb67001: tenant81edcc4fa5554fdf87f6feaf091ee186, run995a079d90584a58a45fd8d988c51f7f,
deal2c2bf2b1-ade2-4051-8dc1-7dd16fcd8f37, client35dfed73-9222-4069-96dc-9b46dbae299e.
Real upload/extraction passed, approval plan409 because authored hybrid fixture
reused staffing assignment_id=team and omitted cost rates. Gate correctly
rejected; no business logic relaxed. a5ee0e8 supplies distinct teams, explicit
source ratesUS10/India5 and nonstaffcosts480/1600, retaining independent
totalprice24000/cost10000. Purepreflight60748 caught missingrates;60535 showed
correct totals/statusok but the harness expected wrong literalcomplete. Corrected
to enumok; literalmoney assertions added before any provider call.
Owned uploaded S3 versions cleaned; persisted fixture/GM retained.

95552 ona5ee0e8: tenant6675646a5113405183102a9343fa36c3,
runffbf8198fb3f4ceab7bd1aaf26723261, deal9b27c56c-4685-4d46-8200-815943cb4433,
clientfdc5fd70-47d5-4d07-ba26-e9e2a8467ccc; allfive approvals reached ready_to_sign.
Packagebb7a45df-511e-4f82-97d0-254b52b7689e signatureblocked/signatories_mismatch:
approved extraction included Alex Example for Client, Casey Example for SmarTek21,
/s/ Alex Example, /s/ Casey Example; executed extraction included only firsttwo.
Price/term/scope matched. Correct refusal retained, no release/actuals claim.
Source document's duplicated authorized/executed name blocks were ambiguous;
1932757 adds explicit single-entry signature blocks and independenttwo-name
assertion BEFORE approvals. Original variation remains an open held-out
extraction quality case, NOT fixed by changing the new fixture. Both exact own
S3 keys/versions cleaned (upload verificationprefix and generated signedkey).
Database rows preserved. Never retry old cleaned uploads as intactdocuments.

Superseded snapshots only. Current entry point: claude-handoff.md.

## Current Checkpoint: 17:45 UTC

HEAD **646419b**, application **0cbb530**. Full backend regression is running
in exec session **45192** against this frozen revision; intended artifact
`evidence/baseline/full-0061.xml`. Check the operation before retrying. No source
changes during this run. Own API8210 session97371/PID12726 and web5210
session19788 remain available; retained journey database is at0061.

Independent QA capacity is now confirmed: `/root/s21_independent_qa` is actively
reviewing in `dealgate-s21-qa-extraction-review`, branch
`s21/qa-extraction-review` at646419b. Owns only `docs/s21/qa-extraction-review.md`;
no tests or runtime mutation. Lead plus ONE light reviewer are active. The older
zero-worker inventory below is the report-time snapshot, not current activity.
QA has reported four static candidates awaiting targeted reproduction: disputed
valued currency can pass scope; replay/confirmation race; ownership-transfer
authorization race; sibling conflict drafts can acquire new tokens silently.
Do not treat these as fixed or as executed failures. Lead will integrate the
bounded report and add focused regressions after the frozen suite finishes.

Weekly quota remains unobservable. Requirement totals remain0/49/2; no release
gate advances. ETA held34-59 active elapsed/42-72 aggregate hours plus external
waiting until independent review and combined results justify a change.

## Latest Delta: Source Conflict Review

0cbb530 removes silentUSD default, retains confirmed history,21focusedtests pass
after3observed currency regressions and a cost-test fixture prerequisite fix.
Browser40089: currencycasePASS15.6s; conflictcasefailedECONNREFUSEDbeforefixture
because lead started tests before API readiness. VerifiedGET/me200 then only
conflictcase90287PASS29.4s; do not call originalcombinedrun allgreen. Readiness
check mandatory before tests aftereveryAPIrestart. API97371/PID12726 serves
0cbb530;old96167/PID10981 verified/stopped/collected143. Latest screenshots now
match truthfulbanner. Nextfullcombinedbackend at frozenHEAD, no feature edits
during that run. Currentuser reportsbudgetresets; ONE existingQAagent capacity
recheck in isolatedread-onlytree, not assumedrunning untilconfirmed. Seeownership.

e75af5c implements2bfbd9f contract: explicit keep/accept review, source-token CAS,
owner/admin API, audit/evidence preservation and unresolved-conflict submission
guards. Initial7HTTP/submission cases red;63affected backend pass25.30s,17UIpass,
typecheck and targetedruff pass. Actual browser26067 passes1case25.9s on e75af5c
plus truthful banner copy: synthetic persisted conflict (NOT live extractor
quality) -> scope blocked -> concurrent human correction ->stale409 ->reload ->
explicit keep ->persisted50000/manual/reload/no conflict. Desktop/mobile reviewed.
OwnedAPI8210 now session96167;81649/PID7576 stopped/collected143;PG0061 retained.
New script/browser/banner/evidence awaiting checkpoint commit; no finite tests
running. Broader exceptions queue/defer/dismiss/bulk review, attempts/OCR/corpus
remain. Next discovered contract conflict: legacy scope builder silently defaults
missing currency toUSD; v3 requires unresolved currency, so test/fix that boundary
without rewriting confirmed history. Requirement totals unchanged. ETAheld.

## Latest Delta: Connected Automation Verified

Application HEAD **31816c9** follows queue fix **fcabb6e**. Both previously dirty
tests are now committed. Focused16 worker/API tests and63 release/source tests
pass; privatePG crash/recovery21501 passes with cleanup. Browser9704 passes
1case/53.0s on31816c9, no retries/timeouts increased: enabled rule -> separate
worker ->70%-40% ->7heads/literal deadlines/history ->disable; desktop/mobile
captures visually reviewed. Old failure/dirty descriptions below are preserved
history, not current blockers. Full T23/T24 remain pending broader assertions;
current45 totals0pass/0failed/37pending/8blocked. No full requirement promoted.
OwnAPI8210 now session81649, old77443/PID770 safely stopped/collected143.
No finite runtime operation active at this checkpoint. RetainedPG0061 unchanged.
Next: extraction exception review/primary OCR and remaining source/lifecycle
automation breadth, then combined regression. Do not repeat fixed fanout work.
Remaining estimate revised34-59activeelapsed/42-72aggregate (one D implementation
hour retired for connected automation), external waits separate. User's original
status snapshot70eccc7 remains auditable. No staged deployment/merge.

Current application checkpoint: **cad16d0f5ab69d34599512b501e3a9f0923e8808** on `feat/s21-forecast`. This handoff was created after the user's immediate status request on 2026-10-02. Preserve later commits and dirty work. Current authoritative whole-requirement/status matrix: [progress-20261002.md](progress-20261002.md). Do not use older `handoff.md` headers or scoreboard `missing` counts as the current buckets.

## Current Failure And Dirty Work

Tracked dirty `api/tests/test_s21_automation_jobs.py`: new `test_changed_source_is_published_first_and_pending_global_refresh_is_not_duplicated`. Completed session54685: **FAIL**, expected one pending job after changed-source publication, observed two; 11 deselected,4.41s. Implementation not yet changed.

Untracked `api/tests/test_s21_automation_project_events.py`: authored release-created-project event expectations, **not run** and hook missing. Own untracked `dev.db`, `evidence/baseline/full-commercial.xml`, `evidence/baseline/automation-desktop.png` preserved; PNG is not reviewed/accepted proof.

Connected automation browser at cad16d0 still fails worker subprocess60s deadline. First run78205 passed business amounts/history then failed immediate mobile resize assertion. Added actual mobile-navigation-ready wait without weakening width assertion; next runs63130/23564 failed earlier worker timeout, so corrected mobile proof remains unverified. Artifacts `tests/e2e/test-results/s21-automation-configured--d48e2-g-through-a-separate-worker/{test-failed-1.png,trace.zip}`; test-results overwrite on runs, preserve before another browser attempt.

Root cause reproduced: plan change queues global refreshes, source publication queues duplicate dependent refreshes already pending. Latest batches12+11 jobs exceed60s. cad16d0 target-only identity lookup reduced97SELECTs/11sources to9SELECTs/1source but did not cure fanout. Next fix: prioritize changed-source job; coalesce only equivalent still-pending current-rule/source-version refreshes that will read new global state. Preserve immutable completed history and watermark checks. Document this contract and pass focused test before browser rerun. Do not raise timeout/retry assertions to green.

Latest large regressions predate0061: backend81278e1 B59; web28a7a28 W415. Subsequent77 affected backend,15 UI/typecheck and69 targeted-source related cases passed; not a new combined full regression. Actual private PG worker crash proof02fe890 succeeded with source/draft/job rollback and recovery, exact2publications/two draft revisions/seven heads/audit chain. No tests rerun just to generate this report.
# Connected Attempt 62524: Failed On 1932757

Completed exit1 before approval: exact signatory identity assertion received
`Alex Example (Client)` and `Casey Example (SmarTek21)`. Full persisted log:
`evidence/baseline/connected-20261002-c.log`. Exact owned S3 cleanup completed.
Do not retry the unchanged fixture as a fix. Real wire schema had only strings
while the stub used typed name/role objects. New dedicated-schema test4276
reproduced missing typed entry; targeted adapter/signature/extraction run99959
passes after typed schema/decoder/prompt fix. Provider revalidation still pending.

