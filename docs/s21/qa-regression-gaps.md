# Independent Regression Gap Inventory

## Scope and Method

Reviewed `922c4b9d6207d0c89ba682c2937af5ad566661f0`, branch
`s21/qa-regression-gap`, on 2026-10-02. This is a bounded source/artifact review,
not a test run. No application modules were imported, no tests collected or
executed, and no runtime, database, cloud, or other worktree was changed.
Only this report is added. Existing evidence is attributed, not independently
reproduced. Finding a related test does not establish equivalent coverage.

Static inventory commands:

```sh
rg -n 'xfail|pytest\.mark\.skip|pytest\.skip|skipif' api/tests
rg -c '^@pytest.mark.xfail' api/tests
rg -n 'raise AssertionError|pytest.xfail' api/tests/test_s20_*.py
rg -o '<skipped[^>]*' docs/s21/evidence/baseline/full-deletion.xml | sort | uniq -c
```

## Exact Denominators

- **150 inherited xfail cases in 30 files, represented by 138 marked functions.**
  Parameter expansions add four cases for the five missing-GM-input cases,
  six for the seven-endpoint permission matrix, and two for three material-change
  cases: `138 + 4 + 6 + 2 = 150`.
- Of these, **146 expanded cases raise a skeleton AssertionError**. The other
  four are renewal examples importing the absent `compute_trigger_date` symbol
  from `app.services.renewals`; the implemented helper is `compute_alert_date`.
  They are not substantive failing executions of the current helper.
- **One opt-in live skip:**
  `test_bedrock_model_check.py::test_default_extract_model_id_is_live_and_invokeable`
  (`:193`), gated by `LIVE_BEDROCK_CHECK=1`.
- There are also **five PostgreSQL-gated cases**: one audit immutability test,
  one concurrent-approval test, and three migration-parity tests. They are not
  the one skipped live check in a run configured with migrated PostgreSQL.
- The stored `full-deletion.xml` has 1,542 cases, one failure and 151 JUnit
  skipped entries, comprising 150 `pytest.xfail` and one `pytest.skip`.
  Thus its pass count is 1,390. This historical artifact is not a current run.
  `postgres-final.xml` records five tests without failures/skips;
  `extract-final.xml` records 70 without failures/skips. Neither retires the
  inherited xfail inventory or proves a new release.
- Outside that pytest denominator, legacy
  `tests/e2e/specs/s20/t44-full-journey.spec.ts:47` still contains **11 skipped
  browser steps**. Do not describe the repository as having only one skip.

## Priority Findings

### Extraction and Live Evidence

`test_bedrock_extract_real.py:50` uses `_FakeRuntime`; its real adapter assertions
validate request schema, tool use, error handling, malformed provider output and
field provenance, not a live model. `test_textract_fallback.py:141` injects
`StubTextract` and `StubBedrock`; it tests OCR dispatch and persisted fallback
state, not recognition quality. `test_sow_extract.py:178` verifies unconfirmed
fields, page references, persisted versions and audit; `:356` requires confirmed
fields before submission. These are meaningful replacements for parts of
extraction-recovery, but not live held-out scans, hostile instructions, conflicting
commercial terms, or manual override preservation on re-extraction.

The opt-in live check invokes model discovery and a model invocation with the
configured credentials/region. Even when enabled, it does not send a held-out SOW
through upload, OCR, extraction, confirmation, seven-profile validation and
governance. Keep **S21F:T16/T24 and FC-09 missing**, not closed by the filename
`extract_real` or an invocation ping. `scripts/s21_real_journey.py` does include
an actual upload/extract path, but one attributed journey is not that adversarial
evaluation corpus. Existing success logs remain lead-owned evidence.

### Scan, Resume and Source Events

`test_hubspot_backfill_scan_generation.py` contains **four test functions**, not
the 22 cases attributed to that filename in `s20-carryover.md:17`. It asserts
healthy completion, pagination failure preventing archival, a subsequent *new*
generation archiving missing rows, and a future-created row surviving archival.
The last case (`:162`) seeds a year-2999 timestamp; it is not concurrent webhook
insertion during a scan. Watermark tests (`test_hubspot_sync_watermarks.py:124`,
`:153`) assert generation monotonicity and stale-completion refusal.

No inspected replacement proves same-generation persisted checkpoint resume,
overlapping scan sweeps, filtered scan archival isolation, or rollback restoring
archived state. `test_hubspot_intake_dedupe.py:70/:126` really checks one event/
opportunity/audit and replay after a dropped acknowledgement. Its `:103` checks
processed timestamps after success, not a forced partial-commit rollback with
mirror/audit/outbox atomicity. Keep **CO-07/T27/T28/T29/T43 missing** at that scope.

`test_s21_consumer_health.py:16/:40` adds meaningful quiet-consumer and injected
handler-failure tests: heartbeat without fabricated processed watermark, and
poison work neither acknowledged nor represented by a healthy heartbeat.
These do not measure 15 real events within 120 seconds, tick-boundary latency,
real visibility-timeout replay, DLQ/alarm delivery or human canary freshness.
The source-worker changes being built after this baseline were not reviewed.

### Release, Financial and Renewal Scope

`test_release_gate.py:263/:321/:336/:351/:365` exercises the real release gates,
refusal without side effects, successful project/audit creation and all three
required events. `:391` proves project-link idempotency; `:420` refuses a
superseded package. `test_signed_sow.py:349/:405/:488` asserts executed price and
signatory mismatches with real service logic and injected extraction/provider
boundaries. These are substantive local coverage, not a finished multi-role
browser journey, concurrent release replay, or invalidated-review recompletion.

The local `s21_real_journey.py:196` path verifies signed upload, acceptance,
release and forecast. It does not import known monthly actuals into that same
released project. `s21_forecast_journey.py:104` separately imports/corrects
financial facts. Joining their names does not prove S20:t44 or **S21F:T17/T30/T41**.

The financial replacement is explicitly split:

- `test_forecast.py:282` checks a 10% margin creates a recovery task/notifications;
  `:340` preserves prior remaining hours; `:481` reads history, but its history
  assertion has one row, not two immutable historical updates.
- `test_s21_financial_actuals.py:50` checks two immutable revisions and one current
  correction; `test_s21_financial_actuals_independent.py:113/:131/:210` covers
  conflict/failed replay and corrections after detachment. These concern the new
  FinancialActual ledger, not the old ActualPeriod import.
- `test_actuals_import.py:313` explicitly expects repeated period/line import to
  **update the existing row**, contrary to the old skeleton's never-update-old
  expectation. Do not mark the latter replaced without an explicit contract and
  legacy data-path reconciliation. Retention tests preserve old facts and
  baselines on deletion; they do not prove arbitrary later writes cannot mutate
  a project baseline.

**Concrete source-level renewal conflict, not merely a missing test:**
`app/services/signed_sow.py:92/:910` uses `_RENEWAL_LEAD_DAYS = 60` when opening
a renewal at release. `test_signed_sow.py:613` asserts that obsolete calculation.
Its March 31, 2027 term end therefore expects January 30, while the two-calendar-
month contract and `test_renewal_alert_date.py:29` require January 31. The passing
calculator tests do not establish the release consumer uses that calculator.
No production fix or executable reproducer was added under this report-only scope.

## All 30 Inherited Groups

Every file below is `api/tests/test_s20_<suffix>.py`; counts are expanded cases.
References are source-inspected assertions, not new pass claims. All whole-group
replacement/acceptance states remain **missing**; individual bounded assertions
may already exist as described. This does not mean all implementation is absent.

| Suffix | Cases | Meaningful inspected evidence | Remaining difference / v3 mapping |
| --- | ---: | --- | --- |
| `baseline_forecast_actuals` | 5 | Release baseline creation; forecast recovery/history; new ledger corrections, as above | Legacy immutable facts, two-update history, full baseline nonmutation; FC-06/CO-05, T21/T41 |
| `ceo_conditional` | 5 | `test_gm_assessment.py:33/:75` floor decisions; `test_ceo_exception.py:282` records conditions/expiry | Recording a condition/expiry is not enforcing it at release; material-change invalidation remains; S21-06/16, T06/T14 |
| `client_rollups` | 5 | `test_hubspot_pipeline_query_service.py:220` currency/agreements; `test_s21_pipeline_independent.py:102/:185` no-match/owner population | Multiple owners and exact closed-lost UI wording not established; DG-02/S21-09, T09/T10 |
| `extraction_recovery` | 5 | Upload/manual-required/confirmation tests above | Re-extract preservation, adversarial/live corpus and link-existing UX; FC-09, T16/T24 |
| `filter_combinations` | 4 | `test_s21_pipeline_population.py:71` exact owner/stage intersections and account/summary population | Not owner/BU/date intersection, UI chip/Back/saved-view or live mapped BU parity; S21-09/11/12, T09/T44 |
| `filter_dates` | 6 | Independent three-page membership `test_s21_pipeline_independent.py:79` covers readiness/attention, not dates | No inspected replacement for full preset, missing-date, timezone-echo and boundary matrix; T09 |
| `freshness_injection` | 5 | Watermark stale/failed tests `:81/:99`; consumer-health quiet/poison checks | Wall-clock drain, actual DLQ/alarm/canary remain; OP-01/04, CO-06, T33/T36/T42 |
| `gm_incomplete_inputs` | 7 | `test_gm_assessment.py:50`; `test_s21_commercial_independent.py:100/:274` unknown-cost/consumer nulls | Five exact absent inputs plus Finance HTTP refusal and Command Center state are not one calculator test; S21-17, T15/T21 |
| `gm_thresholds` | 5 | `test_gm_assessment.py:33/:75`; policy-version thresholds and Decimal commercial tests | Engine coverage is meaningful; end-to-end float exclusion/each exact legacy boundary not fully mapped; S21-17, T13/T21 |
| `integrations_truthfulness` | 5 | Watermark unknown/stale/failed service assertions | Config-derived HubSpot/storage/signature/Cognito integration rows not independently matched; OP-01/FC-12, T27/T42 |
| `many_sows_per_deal` | 6 | `test_sow_id_scoping.py:62/:151` row/model isolation; pipeline sibling/archive `:151/:163` | Complete package decision/version isolation and all headline ordering still require direct cases; DG-06, T17/T32 |
| `material_change_invalidates` | 6 | `test_sow_lifecycle.py:230` version identity/supersession; release superseded refusal | Does not execute price/scope/staffing changes with prior approvals, reapproval, CEO invalidation and preserved audit; S21-03/16, T03/T14 |
| `nda_msa_rules` | 5 | Pipeline agreement presence `:238`; `ApprovalReadiness.test.ts:25` nonblocking note | Legal verification transition and four-surface fact parity not established; DG-05, T17 |
| `owner_resolution` | 6 | `test_hubspot_owners_mirror.py:71/:116/:138`; sync-edge owner rename/unresolved; source-observation independent owner fields | Mirror ingestion is not all UI/account-owner/no-login parity; S21-10/12, T10 |
| `ownership_and_rollup` | 3 | Source-observation separate local assignee; pipeline archived/sibling controls | Exact worst-open ordering and separate archived-count contract not fully matched; DG-02, T09/T17 |
| `permissions_uniform` | 10 | CEO nonrole 403, actual-import role gates, dashboard owner scope, independent forecast/fixture security | Not equivalent to seven-endpoint matrix plus search/export parity; Cognito verifier is mocked; FC-11/12, T25/T32 |
| `release_authorization` | 5 | Real three-gate service, project link and executed mismatch tests above | Full release retry/concurrency and connected project/actuals journey remain; DG-06/CO-05, T17/T41 |
| `renewals_calendar_months` | 8 | `test_renewal_alert_date.py:29/:47/:71/:109/:134` calendar/clamp/short/weekly/timezone | Release uses 60 days; helper weekly dates do not prove acknowledgement stops worker sends or unverified extension rejection; S21-16, T14 |
| `report_dependency_failure` | 3 | `web/.../Reports.test.tsx:269/:285` rejects 503/403 as empty success | Mocked Reports UI is not Command Center agreements-dependency failure with surviving pipeline plus health link; FC-12, T27 |
| `report_scale` | 4 | `test_reports_turnaround.py:69/:154` null/median; query-service bounded SQL count | No declared 120-row legacy report proof here; no v3 10,000-deal/1,000-SOW/24-bucket latency proof; T31 |
| `report_totals` | 5 | `test_s20_w4_session6.py:208/:362/:416` reconciliation/BU unavailable/CSV header | Export header count is not exact exported row population; report filters/export UI remain gaps per reports-regression.md; FC-11, T25 |
| `scan_resume` | 5 | Four scan-generation tests plus watermark stale generation guard | Same-generation resume, overlapping sweeps, filtered scope, rollback not proved; CO-07, T43 |
| `security_boundaries` | 8 | `test_error_cache_control.py:59` real API error headers; `test_hubspot_signature.py:25/:34` HMAC; Cognito adapter rejection | Error headers not CloudFront success/error forwarding; HMAC not replay; stub verifier not signed JWT issuer/audience/use/expiry matrix; T32/T38 |
| `signature_nda_msa_rule` | 3 | Nonblocking readiness note and release path without separate agreement gate | Four-surface consistency, code-rule provenance and Legal verified state not proven together; DG-05/06, T17 |
| `signature_verification` | 5 | Signed price/signatory diff, unsigned evidence rejection, declined/expired audits | Expire/retry no-duplicate provider send and all-surface NDA/MSA parity remain; DG-06, T17/T41 |
| `source_dedup` | 4 | `test_hubspot_intake_dedupe.py:70/:126` repeated event and ack-drop replay | Faulted transaction rollback of mirror/audit/outbox and actual concurrent distinct-event processing not established; CO-07, T27/T43 |
| `stage_reconciliation` | 3 | `test_s20_pagination_vs_totals.py:112`; pipeline qualified stage identity `:139`, unknown bucket `:95` | Meaningful population coverage, not live renamed-source and UI parity; S21-09/12, T09/T10/T43 |
| `stale_package_refused` | 3 | `test_stale_package_hash.py:151` mismatch ->409 | `:199` permits omitted hash; prior-revision decision plus current-version response payload not asserted; S21-03/05, T03/T05 |
| `sync_edge_cases` | 1 | Seven other tests in this file are real; dedupe replay/consumer poison assertions elsewhere | The marked worker-crash/cursor case remains a direct skeleton; CO-07, T43 |
| `upload_interrupt_recovery` | 5 | `test_sow_upload_router.py:241/:497` dedupe/failed-job retry; `test_sow_upload_binding.py:92` bound deal | Not multipart offset resume, process restart with approved-version immutability, or binding across every step; DG-04, T28 |
| **Total** | **150** | **138 functions + 12 expansions** | **No blanket retirement or xfail-to-pass reclassification justified** |

## Reconciliation With 51 Requirements and 45 Scenarios

The v3 scoreboard's requirement state snapshot is preserved, not promoted by this
inventory: **44 missing + 7 blocked = 51**. Exact IDs in those states:

| State | IDs |
| --- | --- |
| missing | S21-01, S21-02, S21-03, S21-04, S21-05, S21-06, S21-07, S21-08, S21-09, S21-10, S21-11, S21-12, S21-13, S21-14, S21-15, S21-16, S21-17, S21-18 |
| missing | DG-01, DG-02, DG-03, DG-04, DG-05, DG-06 |
| missing | FC-01, FC-02, FC-03, FC-04, FC-05, FC-06, FC-07, FC-08, FC-09, FC-10, FC-11, FC-12 |
| missing | OP-03, CO-02, CO-03, CO-04, CO-05, CO-07, CO-08, CO-09 |
| blocked | OP-01, OP-02, OP-04, OP-05, CO-01, CO-06, CO-10 |

`acceptance.md` defines all 45 scenarios and still labels their specification
entries `not_run`; newer partial evidence resides separately in the scoreboard
and run records. Neither 150 xfails nor a green targeted replacement suite is
the denominator for those 45 compound scenarios. Every scenario is reconciled
below once, with no new acceptance claim:

| S21F scenarios | Relation to inherited coverage / remaining proof |
| --- | --- |
| T01, T45 | New deletion/trusted-cleanup suites, not a legacy xfail replacement; all-state/storage/late-worker connected proof still separate. |
| T02, T03, T04 | Workspace/version/owner tests overlap; complete persisted navigation, revisions and truthful editors remain broader. |
| T05, T06, T07, T08 | Routing, conditional CEO and permission fragments overlap; dated OOO, real-identity repair and real mail delivery are distinct. |
| T09, T10, T11, T12 | Filters/owners/rollups overlap; tracking, notes, alerts and persisted UI behavior are not implied. |
| T13, T15 | Financial thresholds overlap; calendar oracle and seven complete model lifecycles are additional requirements. |
| T14, T20 | Material-change/renewal fragments overlap; effective signed amendments and scope conversion are additional. |
| T16, T24 | Extraction recovery/live gaps above; held-out evaluation and persisted automation remain required. |
| T17, T30, T41 | Release/signature/actual fragments overlap; eleven skipped legacy journey steps and the combined current journey remain distinct. |
| T18, T19 | New Forecast views/oracles; no legacy reporting skeleton establishes five persisted views or accepted six-account fixture parity. |
| T21 | New ledger and financial engine tests are useful; legacy actual-period semantics and matched same-basis coverage remain separate. |
| T22, T23 | People demand/capacity/sourcing have no replacement in the inherited xfail groups. |
| T25, T32 | Permissions/export/security overlap; full row/field/snapshot/tenant equivalence cannot be inferred from separate role gates. |
| T26 | Accessibility/responsive full-flow behavior is not proved by backend skeleton replacements. |
| T27, T28, T29, T43 | Source faults/scan resume/transactional recovery overlap; checkpoint/restore/concurrency gaps above persist. |
| T31 | Query-budget assertions do not meet the specified representative load and latency contract. |
| T33, T34, T35, T36, T37, T38, T42 | Operational/deployment/mail/Liberty/human evidence cannot be substituted by unit tests or historical statuses. |
| T39, T40 | Existing populated watcher/approval population tests overlap; exact browser destination membership and current combined proof remain separate. |

S20 carryover remains **65 historical rows**, not 65 current passes: its reported
36 staging-verified, 11 local fixed/tested, 5 missing, 2 blocked and 11 deferred
sum to 65. S20:T32 freshness is not S21F:T32 authorization; S20:T34 dedupe is not
S21F:T34 mail; S20:t44 journey is not S21F:T44 BU. CO-02 remains **missing** until
the gaps and attributable full applicable regression evidence are reconciled.

## Next Evidence Needed

Prioritize executable fault cases for same-generation resume/commit boundaries;
a held-out live extraction/OCR corpus with retained overrides; release-to-renewal
calendar correctness; the same signed project's immutable baseline and known
monthly actuals; and authenticated list/search/export field and row equivalence.
Retire an individual skeleton only after preserving its requirement/assertions
in an attributable replacement and explicitly resolving changed semantics.
Do not remove xfails, weaken legacy assertions, or mark the full contract green
merely to reduce the inherited count. This report changes no test outcome.
