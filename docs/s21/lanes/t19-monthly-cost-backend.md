# T19 Monthly Staffing Cost Backend

Branch s21/t19-monthly-cost starts at contract 934da7e. Prior preview branch
2f4d5d9 preserved. Scope: calendar.py, new monthly staffing tests, this report.
No database, API, provider, schema or deployment operations.

## Contract Implemented

StaffingAssignment appends cost_rate_basis and cost_proration so existing
positional construction remains compatible. Absent basis defaults to hourly for
old typed JSON. Explicit null is unresolved, adds missing cost_rate_basis and
leaves cost unknown; it never silently changes an unconfirmed draft to hourly.
Only hourly/monthly/null and full_month/null proration are accepted.

Monthly per-person cost is cost_rate * quantity * allocation once per affected
complete month. Paid hours remain calendar-derived and do not multiply salary.
Assignment and term clipping both require explicit full_month cost policy on a
partial month; absent policy leaves that month's cost unresolved. Billing
proration is independent. Hourly costs retain their prior paid-hours calculation.
Confirmed calendar coverage, currency, amount and cost version remain required.
Missing version retains existing incomplete-row behavior rather than inventing
authority. Monthly rows reject legacy hourly ResourceInput conversion.

## Evidence

Tests authored before calendar edits. Baseline session17631 exited1 with all19
initial cases red because cost_rate_basis did not exist. Lead then clarified
explicit-null draft semantics; corresponding rejection case became an
unresolved-draft assertion before implementation.

First affected set session47423 passed188 cases. Added commercial component and
schedule JSON roundtrip plus invalid Decimal tests. Expanded session43969 had
191 pass/1 fail: test used an incorrect positional StaffingRate constructor;
fixed fixture to explicit named arguments without changing assertions.

Final session40076: **192 passed in4.61s**, including23 new tests, command:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest tests/test_s21_monthly_staffing_cost.py tests/test_s21_calendar_schedule.py tests/test_s21_commercial_profiles.py tests/test_s21_commercial_independent.py tests/s21_acceptance/test_company_x_forecast_oracle.py -o addopts='' -q -p no:cacheprovider
```

Independent oracle: six people at4800 monthly cost produce28800 each month and
172800 over October2026-March2027 despite unequal paid hours. At8000 monthly
billing, commercial schedule gives48000 revenue/28800 cost each month with no
duplicate PeriodCost. Half/quarter allocation, partial bounds, explicit full
month, null basis, missing calendar/currency/version, invalid decimals and old
snapshot hourly defaults are covered. Component and computed schedule typed JSON
preserve the monthly basis. Ambient Decimal precision does not change results.

This is pure backend evidence only. Lead owns editor changes, all12 preview
preflight, persistence/worker/browser proof. T19 remains pending.
