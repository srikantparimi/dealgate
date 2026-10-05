# Independent Company X Demand QA

Baseline: `7f984593d001e61954fb79a896ae01744cf8cb5b`.
Branch: `s21/qa-company-demand`. Bounded review: approximately 15 minutes of
authoring/review, with execution serialized behind the lead's backend suite.
Only this report and `api/tests/test_s21_people_company_x.py` are owned here.

## Method

Eight independently authored cases call actual `save_plan`,
`publish_plan_demand`, `import_workforce`, `demand_sources`, `availability`, and
`demand_allocation` services against private in-memory SQLite with foreign keys
enabled. There are no mocked feature responses or imported worker fixtures.
Production code and existing assertions remain unchanged. API authentication,
PostgreSQL concurrency, migrations, browser and staging are not exercised.

The synthetic Company X source explicitly contains two US and five India
full-allocation people from 1 November 2026 through 30 April 2027 inclusive.
Hybrid root, children and assignments share authoritative source/version/policy
identities; each child and assignment use their location's explicit calendar
and matching IANA timezone, with child terms inside the root. Financial pricing
and cost evidence intentionally remain unresolved: this is a cost-free staffing
oracle, not commercial or forecast acceptance.

Literal expected results do not use production output as a calculation oracle:

- Four cases change descriptive probability from 70% to 20%, 100%, 0%, or
  unknown. Every selected current publication still requires 2 US + 5 India,
  seven people and seven FTE in each of six months. An explicitly imported empty
  roster means a known seven-FTE gap, not absent supply evidence.
- A revised source moves the interval to December through May and changes US
  quantity to three. The old publication becomes stale with no old fresh lines;
  republishing yields eight people/FTE while old quantities and dates survive
  unchanged in immutable history. Manual skills, level and evidence survive.
- An earlier competing account takes one US and one India person from a global
  roster of one US + four India. Company X has zero US and three India matches,
  a four-FTE gap. Account and Sales filters cannot make those two already matched
  people reappear. The Sales view does not expose hidden source identity or names.
- Seven explicitly retained people with matching stable demand-line commitments
  satisfy the original seven slots without a second capacity subtraction. A
  subsequent increase to eight slots keeps seven retained and only one incremental,
  with a one-FTE gap; no hiring or reservation is inferred.
- Foreign commitments ending 15 November block all seven slots through that
  inclusive date. Capacity becomes available on 16 November. November's peak gap
  remains seven, while later months have zero gap.

## Execution

After the lead's explicit serialized runtime grant:

```sh
env -u DEALGATE_POSTGRES_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest api/tests/test_s21_people_company_x.py api/tests/test_s21_people_allocation_service.py -o addopts='' -q -p no:cacheprovider --tb=short --basetemp=/tmp/s21-qa-company-demand-independent
```

Run from this worktree root. Result: **11 passed, 2 warnings in 17.22s**, exit 0.
Eight new independent cases and three existing allocation-service cases passed;
zero failures, skips or xfails. Both warnings are existing FastAPI `on_event`
deprecations. Runtime was released immediately on process exit. No rerun,
production correction or assertion relaxation was needed.

New node IDs, prefixed by `api/tests/test_s21_people_company_x.py::`:

- `test_company_x_probability_revisions_keep_two_us_five_india[0.20]`
- `test_company_x_probability_revisions_keep_two_us_five_india[1.00]`
- `test_company_x_probability_revisions_keep_two_us_five_india[0.00]`
- `test_company_x_probability_revisions_keep_two_us_five_india[None]`
- `test_company_x_date_and_headcount_revision_replaces_current_not_history`
- `test_company_x_global_competitor_consumes_capacity_before_account_or_sales_filter`
- `test_company_x_retained_people_reuse_own_commitments_and_only_growth_is_incremental`
- `test_company_x_foreign_commitments_roll_off_on_inclusive_boundary`

No reproducible production defect was exposed by these bounded scenarios.
The literal Company X oracle is now locally tested through actual persistence
and allocation services; this is not evidence of full feature acceptance.

## Acceptance Boundary

| ID | State | Boundary |
| --- | --- | --- |
| T22 | missing | Full feature acceptance is not established by these service tests. Retained delivery projects, connected source events, rules/snapshots and browser/staging proof remain outside this increment. |
| T23 | missing | Versioned sourcing drafts, approval/event workflows and their connected proof are not exercised or claimed. |

Managed supply is explicitly not live HR data. Matching remains a versioned
proposal, not an approved staffing policy or reservation. Same-plan continuity
does not establish signed or retained-project continuity. Probability revisions
do not establish financial scenario switching or commercial Forecast Oracle A.
