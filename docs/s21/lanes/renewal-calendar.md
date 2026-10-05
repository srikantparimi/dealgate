# Release Renewal Calendar Fix

Isolated branch `s21/renewal-calendar`, baseline `168b605`. Budget: 20 minutes
of active work, coordinated test slot. Owned scope: renewal creation in
`signed_sow.py`, release renewal tests and this report. Shared renewal helper,
model/schema, approval and signature gates are read-only.

Independent QA identified that signed-SOW release subtracts sixty days while
`services/renewals.compute_alert_date` already implements the accepted two
calendar months with target-month day clamping. The existing release test also
asserted the obsolete sixty-day result.

Tests authored before production change use literal date expectations:

| Approved term end | Required trigger |
| --- | --- |
| 2027-03-31 | 2027-01-31 |
| 2027-04-30 | 2027-02-28 |
| 2028-04-30 | 2028-02-29 |
| 2027-01-31 | 2026-11-30 |

Each boundary case creates a package fixture with internal signoff and delivery
acceptance, creates/verifies an upload and calls the real release service.
Assertions cover the persisted renewal date, audit payload date and intact
audit chain. Provider extraction/mail use existing unit adapters; no live
provider or staging claim follows. The existing distribution/guard assertions
remain intact; only its stale renewal-date expectation changes.

The five selected cases first failed at their literal date assertions: March
31 produced January 30; both April 30 cases produced March 1; January 31
produced December 2. Production now delegates to `compute_alert_date`, deleting
the obsolete sixty-day constant/import and correcting its release docstring.

Verification after the lead assigned the slot: all 17 signed-SOW tests passed.
Combined signed-SOW, renewal helper/service, release gate and legacy S20
authorization/calendar files: **54 passed, 13 inherited xfailed**, two existing
FastAPI lifespan deprecation warnings, 21.41 seconds. No new skips/xfails,
retries, changed guard assertions or weakened expectations. The inherited
xfails are eight calendar skeletons and five release-authorization skeletons;
they are not verified behavior and were not edited in this ownership scope.

Command (from this worktree's `api` directory):

```sh
env -u DEALGATE_POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/Users/srikanthparimi/OfficeApp/dealgate-s21-renewal-calendar/api \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest \
  tests/test_signed_sow.py tests/test_renewal_alert_date.py \
  tests/test_s20_renewals_calendar_months.py tests/test_renewals.py \
  tests/test_release_gate.py tests/test_s20_release_authorization.py \
  -o addopts= -q -p no:cacheprovider
```

SQLite fixtures are private in-memory databases; the dependency executable is
read-only and all source imports resolve to this worktree. No shared DB,
provider, cloud or staging calls. Diff checks passed.

Status: fixed and tested locally, not staging verified. This narrow fix does not
close short-engagement triggers, weekly cadence, extensions, nonrenewal,
end-to-end scheduler behavior or staging acceptance.
