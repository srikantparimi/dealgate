# T18 Selected Empty Account Label

Base133971722cad310598e8071be224e5325b7339d5. Clean owned tree verified before
creating s21/t18-account-label. Only forecast_plans.py, the new focused test file
and this report changed. No integration-tree edits, migration, deploy or providers.

Explicitly selected empty Client now contributes its real account label and the
existing zero-valued account summary. Nonarchived existence and _account_allowed
are required. Organization readers retain existing organization access; Sales
and SalesLeader require an owned scoped plan or live owned opportunity. The
fallback does not add empty accounts to the unfiltered company population or
bypass fixture grants. Missing, archived, expired/foreign/unissued fixture and
unrelated Sales account labels remain unavailable. Source counts remain zero.

Tests were authored first. For observed baseline red, only this worker's service
delta was temporarily removed with apply_patch, then restored before green:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
/Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python \
-m pytest -p no:cacheprovider tests/test_s21_forecast_empty_account.py -q
```

Own api directory. Baseline session53951:3 failed/2 passed, failures are missing
authorized selected account labels. Fixed session21158:5 passed, exit0. Same
assertions preserved; zero revenue/cost, unassessed GM, five quarter summaries,
empty rows/source counts, restricted account absence and company universe all
asserted. No broader suite or browser was run. Heavy slot released after the
finite focused run. Lead owns connected T18 browser proof and final integration.
