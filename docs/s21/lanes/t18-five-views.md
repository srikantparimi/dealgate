# T18 Connected Forecast Views

Current task, 2026-10-03 00:56 UTC. Baseline1339717; no scenario closure yet.
Original acceptance T18 and its six conditions remain unchanged. Parent
FC-01/02/03/04 are not closed by this narrower view proof.

## Ownership

- Lead, feat/s21-forecast integration tree: ResourceDemand, Forecast page,
  focused frontend tests, new connected Playwright proof and evidence/ledgers.
- Governance, s21/t18-account-label in dealgate-s21-actual-coverage, base1339717:
  forecast_plans.py, new test_s21_forecast_empty_account.py, own lane report.
  Explicit selected-account label only; preserve portfolio and fixture access.
- Independent QA: read-only controls, period semantics and existing evidence.
  Two light tasks available; one heavy test/runtime at a time remains the limit.

## Assertions And Independent Expectations

Use owned private0062 runtime, not staging or retained0061 database. T21's
signed prerequisite can be reused without claiming new signature proof.
Create synthetic linked plans and empty account through real fixture/plan APIs;
run the real forecast worker for persisted schedules. Record every new ID.
Do not rerun the completed financial import journey on populated fixtures.

Verify all five views, named account/source drills and Back, scenario/as-of/
horizon/month context, current quarter separately from future, empty/error
recovery, exports and visible controls. Existing focused connected coverage
may supply unchanged staffing-editor assertions, with exact older revisions.
Independent money oracle must be declared before running the browser.

## Current Evidence

- UI regression9231: resource link dropped scenario/as_of/horizon/month.
  One selected test failed;11 unselected tests are not acceptance skips.
- Repair78275: full ResourceDemand test file12 passed/6.64s, no skips.
  No connected proof yet. Only Forecast links inherit those four filters;
  target account/view retained, source pagination deliberately not inherited.
- QA found empty authorized account header falls back to UUID; worker assigned.
- Resource intervals currently ignore period filters. Contract review pending;
  no claim that navigation repair alone resolves temporal demand semantics.

## Repair Checkpoint 01:04 UTC

Contract review confirmed overlap filtering is required, not merely a label.
Regression27826 failed on an outside-period source; repaired23542 passes all25
ResourceDemand/Forecast tests. Full canonical sources remain in editors;
pending/stale/undated demand remains visible. Interval ends are inclusive.
Typecheck95463 exit0. Connected proof still pending.
Workerf443f25 integratedae753de: selected authorized empty-account naming,
5 focused tests green21158 after baseline3fail/2pass53951. No widening of
company account universe. Worker now authors only private API fixture script.

QA found stale selected month after horizon reduction:68907 red,41393 green
26 tests across both UI files. Invalidated month is cleared against the
returned server horizon; a still-valid month survives horizon changes.
Malformed/reversed dates and publication of filtered-out canonical lines also
asserted. Connected navigation spec authored but not yet run; fixture pending.
Fixture author guard repeated the old0062 prefix mistake; caught in review
before execution, worker correcting exact revision. No data was mutated.
