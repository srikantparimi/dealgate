# Command Center Forecast and Portfolio Integration

## Staging candidate

Application commit `a5f3445a8d99c762559426e499f6cd366779592f` is packaged as
immutable AMD64 image `officeapp-dev-api:ccint-a5f3445`, digest
`sha256:a5c3020afad1ec8fd11e3da9d515ba0e16c4d0ee67a08313e8aad786bee861f0`.
The exact saved Terraform plan `/tmp/ccint-a5f3445.tfplan` is 12 add / 14
change / 12 destroy and contains only revisioned ECS task definitions, the
migration trigger, and references that follow those revisions. It contains no
persistent-data, identity, storage, network, DNS or CDN change. The plan awaits
the required human infrastructure approval; staging still runs API revision
110 and the prior SPA.

## Verified baseline

Read-only staging query on 2026-10-13 against API task definition `officeapp-dev-api:110`:

- 83 engagement rows: 78 open and 5 closed.
- Business units: IT Avalon 59, Retro Rabbit 8, ST21 16.
- 420 current allocations and 370 active resources.
- 3,444 allocation actual rows; latest actual month is 2026-09.
- 3 explicit engagement cost rows.
- 0 renewal rows.
- 0 engagement rows linked to an Opportunity.
- 679 non-archived opportunities: 116 open and 262 closed-won.

The earlier reported 81 is the workbook dry-run population, not the current database total. The Command Center must derive its display from current authorized records, never either hardcoded number.

## Metric source map

| Displayed metric | Authoritative source | Included records | Period | Calculation | Drill-down |
| --- | --- | --- | --- | --- | --- |
| Revenue this month | `engagement_forecast.portfolio_month` -> `forecast_payload` | Every permitted open engagement overlapping the month, including imported records | Selected calendar month | Sum authoritative month revenue; actual-to-date comes only from `AllocationActual` for the labeled cutoff | `/portfolio?month=YYYY-MM` with the same BU scope |
| GM this month | `forecast_payload` month lines and cost provenance | Same monthly engagement population; cost-covered subset stated explicitly | Selected calendar month | `(covered revenue - covered cost) / covered revenue`; confirmed/default cost coverage remains labeled | `/portfolio?month=YYYY-MM` |
| Signed backlog | Existing signed commercial schedules plus open imported engagements with bounded effective terms | Authorized signed terms only; exclude recognized actual revenue and unsupported dates | Current date through each effective end date | Remaining scheduled signed revenue after recognized actuals; de-duplicate native and imported sources | `/forecast?scenario=committed` |
| Weighted pipeline | `Opportunity` + saved `HubspotStage.probability` | Authorized, eligible, open, unsigned opportunities; exclude linked engagement/renewal amounts | Selected 3-6 month horizon when scheduled | Eligible amount x saved probability; unscheduled amount stays outside monthly bars | `/pipeline` with the same BU/owner scope |
| People | Portfolio `Allocation`, `Resource`, `rolloffs_from`, `_bench`; published demand for open seats | Authorized active people and current/future allocations; TBC demand is not a person | Current month and next 60 days | Distinct billable people, distinct bench people, ending allocations, and FTE/hours kept separate | `/portfolio?month=YYYY-MM#people`, `#bench`, or `#rolloffs` |
| Needs attention | Pipeline, Portfolio forecast, renewals, approvals and cost provenance | Authorized exception populations; related risks grouped | Current month / last closed month / next 60 days as labeled | Category-specific exposure, margin shortfall or contract value; missing impact remains explicit | Category action URL |
| Revenue outlook | Existing forecast schedules, explicit likely renewals and eligible scheduled opportunities | Mutually exclusive committed, expected renewal and pipeline populations | Next 3-6 months | Cumulative toggles without duplicate source records | `/forecast` |
| Capacity by location | Dated allocations/resources plus published workforce/demand services | Active employment, dated assignments and unfilled TBC demand | Next calendar month | Required and available capacity in matching FTE/hours; headcount separate | `/portfolio` / `/people` location filters |

## Root cause before implementation

`build_command_overview` currently begins with the HubSpot opportunity list and then reads only `Engagement` rows linked to those opportunities. The live database has zero such links, while Portfolio intentionally reads all permitted open engagements. The Command Center therefore drops the authoritative imported engagement population before any financial calculation runs. The old overview also treats its HubSpot Stage-5 table scope as a company-financial scope, which incorrectly applies the table-only restriction to tiles, risk detection and capacity.

The fix will compose existing Portfolio/Forecast/Pipeline services into one permission-aware read model. It will not add a second calculator or require imported engagements to be republished.

## Implementation order

1. Shared overview read model and exact population/drill-down contracts.
2. First-row business tiles and deterministic three-line brief.
3. Financial exception queue and lifecycle populations.
4. Revenue outlook and capacity/location views.
5. Minimal renewal-likelihood and billing-loss policy configuration.
6. Focused local checks, one combined regression, staged migration/deploy, and connected proof.

## Local candidate checkpoint — 2026-10-13 22:01 PDT

The integrated read model is implemented in
`api/app/services/command_center_overview.py`. It starts from permitted open
engagements, including imported rows with no Opportunity link, and composes the
existing Portfolio forecast engine, Forecast schedules, renewal records,
approval assignments and People allocation publication. The Stage 5+ rule is
still confined to `Accounts & engagements`.

Implemented behaviors:

- Five first-row tiles with explicit current/closed-month evidence, cost
  coverage, signed-term backlog, saved-probability pipeline and distinct
  people/FTE/open-seat counts.
- Ranked financial actions for closed-won gaps, roll-offs, GM floor failures,
  uncovered post-SOW forecast, billing loss, user approvals, missing current
  costs and SOWs nearing end without a renewal item.
- Three deterministic brief statements derived from the queue and aggregates.
- Cumulative committed / expected-renewal / pipeline-upside monthly views.
  Proposed renewal value is allocated over its full proposed term before the
  selected window is sliced; unscheduled weighted pipeline remains outside the
  bars.
- Next-month location allocation plus authoritative managed demand/supply.
  Incomplete publications expose required demand but withhold allocated/gap
  conclusions. TBC rows count as open seats, never people.
- Renewal likelihood/proposal evidence and billing-loss/default probability
  settings through migration `20261013_0068_cc_rules`.

Focused evidence on this working candidate:

```text
api: pytest -q tests/test_command_center_accounts.py -x -> 15 passed
api: pytest renewal owner/planning route -> 1 passed
web: CommandCenter + RenewalBoard + S22 Portfolio/P5 -> 41 passed
web: npm run typecheck -- --pretty false -> passed
web: npm run build -> passed (index-cy26KtjL.js, index-B8R_pDti.css)
ruff: changed backend and focused tests -> passed
alembic: PostgreSQL offline 0067:0068 DDL -> passed
```

The full clean-SQLite migration path stops at historical migration 0028 because
that old revision uses an unsupported SQLite constraint alteration. PostgreSQL
migration parity tests require `DEALGATE_POSTGRES_URL`; they were skipped
locally and remain a staging preflight gate. No staging artifact contains this
candidate yet.
