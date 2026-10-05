# Independent QA: First Increment

Run ID: QA-S21F-20261001-1. Bounded budget: approximately 10 minutes.
Branch `s21/qa`; reviewed production source `e041387be438c51fc35eb4804628935ee4e0270c`.
Owned files: this report and `api/tests/s21_acceptance/test_independent_oracles.py`.
No production changes, cloud calls, shared runtime, migrations, staging or browser runs.
QA does not approve the lead's subsequent fixes.

## Findings

1. **P1: test CEO identity can approve an ordinary business package.**
   `api/app/services/ceo_exception.py:382` checks only CEO/delegate authority;
   lines 402-423 never check trusted fixture scope or assigned executive identity
   before recording a decision. The separate `can_decide` function at line 200
   accepts the CEO group. A persisted ordinary package, valid rationale and user
   with both `CEO` and `officeapp-e2e` successfully traverse `decide(..., approve)`.
   Expected HTTP 403; actual no exception, allowing the `ready_to_sign` transition
   at line 437. The regression is deliberately red.
2. **P1: legacy task creation routes real work to test identities.**
   `api/app/services/approval_workflow.py:50` returns `None` for packages without
   assignments, activating `api/app/services/approvals.py:340` onward.
   `_users_in_group` at line 299 checks raw role membership only. Calling
   `submit_package` without routing creates an `approval.awaiting` task owned by
   an ordinary business package's test user carrying `Delivery`. Expected no
   test-owned task; actual one persisted task. This bypass remains relevant to
   legacy packages even where current UI callers supply routing.
3. **P1: task-linked approval reminders bypass queue and dispatch containment.**
   `api/app/services/test_fixtures.py:156` returns immediately for every entity
   other than `approval_package`. The production approval nudge at
   `worker/alert_scheduler.py:430` queues `approval_pending` with entity `task`
   at line 440. A historically contaminated business approval task therefore
   passes the queue guard and `worker/notification_sender.py:146` dispatch guard.
   Separate regressions reproduce both boundaries: queue returns normally, and
   dispatch sends one message to the test identity through the isolated SES sink.
   Expected rejection/suppression and zero provider sends. The task's existing
   `task.created` audit identifies its actual approval package.

Issuance/scope static review: `create_fixture` requires enabled nonproduction
dev seeding, persisted test SystemAdmin, explicit tenant, bounded lifetime and
known test participants. It creates a new client/deal and writes provenance in
the caller's transaction. `reviewer_scope` checks environment, tenant, expiry,
issuer authority, owner, deal identity, uploader, CRM associations and archive
state. No additional concrete issuance defect was established in this bounded
review. This is not independent execution of every issuance or permission case.

## Independent Financial Evidence

Oracle B uses only stdlib `date.toordinal/fromordinal`, weekday and `Decimal`
to derive expectations. No production return value becomes an expected number.
The ten synthetic holiday dates are copied from the authoritative directive.

| Month | Billable Days | Paid Days |
| --- | ---: | ---: |
| 2026-10 | 21 | 22 |
| 2026-11 | 19 | 21 |
| 2026-12 | 22 | 23 |
| 2027-01 | 19 | 21 |
| 2027-02 | 19 | 20 |
| 2027-03 | 23 | 23 |
| 2027-04 | 22 | 22 |
| 2027-05 | 20 | 21 |
| 2027-06 | 21 | 22 |
| 2027-07 | 21 | 22 |

Independent totals: 207 billable days / 217 paid days; 16,560 billable and
scheduled hours / 17,360 paid hours; USD 1,656,000 revenue / 1,041,600 cost;
GM `0.3710144927536231884057971014`. Monthly production quantities, money and
existing GM engine results match those expectations. Additional passing cases
cover leap and non-leap centuries, year boundary, one paid holiday, weekend-only
month boundary, `date.max`, fractional allocation/headcount applied once, caller
Decimal precision isolation and seven disjoint partition conservation checks.
No calendar arithmetic defect was established in this sample.

Oracle A independently allocates USD 420,000 / 210,000 over six service months
and groups dates by year/quarter. Full/weighted monthly revenue is 70,000/49,000;
Q4 Expected 122,000; Q1 147,000; Q2 49,000; next two full quarters 196,000.
Whole proposed term weighted revenue/cost is 294,000/147,000, GM 50%.
Shifting November-April to December-May preserves the full 420,000 fee.
This is an expectation artifact only: no production Forecast or People result
was tested, and the specified two US/five offshore headcount remains a separate
acceptance requirement.

## Execution Record

Lane-owned Python 3.14 venv `api/.venv`, installed with
`api/.venv/bin/pip install -e 'api[dev]'`. No shared environment was used.
SQLite `:memory:` fixtures, synthetic identities, real services, isolated SES
delivery sink; `DEALGATE_POSTGRES_URL` removed from each pytest invocation.
Frontend/API/worker deployments and migrated schema: not run/not applicable.

```sh
env -u DEALGATE_POSTGRES_URL api/.venv/bin/pytest \
  api/tests/s21_acceptance/test_independent_oracles.py -o addopts=-ra -q
```

Expected/collected/executed 13; passed 9; failed 4; skipped 0; xfailed 0;
not-run 0 within this selected suite. Exit 1; 23.11 seconds. Two existing
FastAPI startup deprecation warnings. No retries, skips, xfails or weakened
assertions were added. A subsequent edit made the monthly margin expectation
explicitly independent of the already-checked production money fields; rerunning
`-k 'calendar or company_x'` passed 9 with 4 security cases deselected (1.98s).
Security assertions and production code were unchanged after their red run.
Ruff passed for the new test file.

Collected node prefix (pytest rootdir `api`): `tests/s21_acceptance/test_independent_oracles.py::`.
Actual collected suffixes:

- `test_independent_calendar_b_monthly_money_hours_and_margin`
- `test_independent_company_x_a_even_months_quarters_and_shift`
- `test_independent_calendar_boundaries[start0-end0]`
- `test_independent_calendar_boundaries[start1-end1]`
- `test_independent_calendar_boundaries[start2-end2]`
- `test_independent_calendar_boundaries[start3-end3]`
- `test_independent_calendar_boundaries[start4-end4]`
- `test_independent_calendar_boundaries[start5-end5]`
- `test_calendar_partition_conserves_independently_counted_quantities`
- `test_test_ceo_cannot_approve_business_exception` (failed)
- `test_legacy_task_path_excludes_test_reviewer_from_business_package` (failed)
- `test_task_linked_approval_reminder_blocks_test_identity[queue]` (failed)
- `test_task_linked_approval_reminder_blocks_test_identity[dispatch]` (failed)

## Assigned Scope Status

| Requirement | State | Proof / Remaining Work |
| --- | --- | --- |
| S21-07 / OP-03 | missing | Four red regressions above; lead must fix and independently recheck containment. |
| S21-15 | fixed and tested | Bounded calendar arithmetic only; eight passing calendar checks. Persisted calendars/UI/staging T13 remain not_run. |
| S21-17 | missing | Integrated pricing workflow and all profiles were outside this increment. |
| FC-02 / FC-04 / FC-05 | missing | Oracle A independently established; production account/company Forecast reconciliation T19 remains not_run. |

Full S21F:T07, T13, T19 and T32 acceptance is not claimed. Historical invalid
decision remediation, real tenant/API permissions, immutable Postgres audit
enforcement, full upload/approval/browser journeys, real outbox worker delivery,
and deployment remain unverified here. Other scenario IDs were not assigned or run.
