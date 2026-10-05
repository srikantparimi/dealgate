# T19 Explicit Preview Fixture Confirmations

Branch s21/t19-confirmed-preview starts at a194941; monthly backend branch
89851d4 is preserved. Owned files are the new pure confirmed-input helper,
its new focused tests and this report. No application files changed.

confirmed_records(location=..., timezone=...) wraps the original accepted
records with a fresh deep copy. Only Atlas's two sources receive a declared
synthetic Mon-Fri eight-hour calendar (no holidays, 2026-2028 coverage), caller
location/timezone, 4800 monthly cost per person and a fixture cost version.
Cost proration stays unconfirmed because these terms contain complete months.
Six people at 8000 monthly revenue and 4800 monthly cost remain the original
48000/28800 team figures. The duplicate six PeriodCost rows are removed only
after checking the original exact source shape. No other source is modified.

Original names, profiles, dates, revenue/cost literals, probabilities, lifecycle
labels and evidence remain intact. Atlas retains its original source unknowns
separately; the new confirmation is labelled synthetic fixture authority, not
extraction or HR approval, in cost basis, evidence and fixture assumptions.
The original records() remains unresolved. The helper invokes strict original
preflight before returning so incomplete or changed monthly amounts fail closed.

Tests authored before helper cover all12 literal monthly money values, strict
month comparison through preflight, source/oracle fingerprints, unconfirmed
original failure, no aliasing, exact calendar metadata, two explicit geographies
and invalid geography rejection. Authorized focused session9493 passed all6
cases in3.27s, exit0. Tests were authored first; initial missing-module execution
was not run while the lead held the serialized slot. No database, API, worker,
provider or deployment operations.

Executed focused command from api directory:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest tests/test_s21_preview_confirmed_inputs.py -o addopts='' -q -p no:cacheprovider
```

This fixture preparation does not close T19 or replace persisted connected proof.
