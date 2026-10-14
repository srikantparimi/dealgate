# Command Center Forecast and Portfolio Integration

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
