# T19 Accepted Preview Inputs

Initially authored without execution. Clean prior branch preserved atf7c17d7; new
s21/t19-preview-inputs starts integration343c764371512e6f71636209de4cf7599ba15257.
Owns only scripts/s21_preview_inputs.py and this report. No database, API,
worker or provider calls performed. Lead owns persistent fixtures.

Pure records(location=..., timezone=...) exports the original twelve named sources
across Company X, Harbor Health, Northstar Retail, Atlas Bank, Cedar Labs and
Meridian Group. Exact preview names/models/evidence, probabilities, service months
and monthly revenue/cost literals remain separate from production calculations.
Committed->signed, planned->tentative, draft->needs_review map existing lifecycles;
original draft assumptions and probability provenance are retained. No financial
actuals or signature proof is inferred from preview signed prerequisites.

Five actual commercial profiles are used: fixed_assignment, recurring_msp,
milestone, calendar_staff_aug and unit. Monthly staffing is never relabelled as
fixed assignment. Cedar uses140 per accepted story point with300/120 monthly
quantities; MSP uses full-month agreed fees; Northstar milestone values remain
40000/60000/50000/30000 with preview proportional costs24000/36000/30000/18000.
Company X signed preview cost is14000, NOT the separate connected fixture10000.

EXPECTED is an independent literal15-month, five-quarter, three-scenario matrix,
next-two/next-four totals and six account next-two Expected totals. Key preview
anchors:October208500; Q4Expected700700; Q1449400; Q2217000; future666400,
futureSigned174000 and futureUpside894400. These are source facts, not values
captured from forecast output. Each input's revenue/cost tuples support full
per-source monthly comparison. preflight(items) parses/calculates every model,
requires full completeness and compares exact month/revenue/cost to those literals.
It raises on any missing basis; no missing-cost substitution, source skip or zero
defaults are accepted as a passing fixture.

## Explicit Unknowns

Atlas signed and extension evidence gives six engineers,48000 combined monthly
fee and28800 monthly team budget. Inputs preserve calendar_staff_aug and
8000/person/month; canonical calculation currently needs a work calendar and
loaded hourly cost/version not provided by this evidence. They remain None,
not fabricated. Declared28800 monthly budget is retained as PeriodCost evidence;
it must not later be added on top of invented staffing cost. Strict all-source
preflight is expected to remain unresolved for these two sources until lead
addresses the actual monthly-cost-basis contract/schema gap. T19 is not currently
unblocked merely because the other profiles can be represented.

HTML has role/bench planning details but no universal production geography or
work-calendar evidence. Caller must explicitly supply synthetic financial
location/timezone; records label this fixture-only allocation, not extraction or
production truth. Milestone month-start dates represent named preview months,
not known delivery/acceptance days; acceptance wording explicitly says details
were not supplied. No invoice/recognized-revenue references are invented.
Other preview role mixes are not made into hourly assignments whose costs would
double-count the supplied total budgets. Financial preview is not a complete
People calendar/continuity fixture.

Lead-approved next step: retain Atlas unknowns and assess true monthly staffing
cost capability rather than request arbitrary hourly inputs or weaken the fixture.
After runtime grant, first focused pure validation should identify exact unresolved
source IDs and assert all other sources' literal monthly costs/revenues; a fully
passing12-source preflight is required before persisted production acceptance.

## Bounded Pure Validation

Authorized command used the private QA Python interpreter with
PYTHONDONTWRITEBYTECODE=1 and PYTHONPATH=api:scripts. It constructed records with
explicit US/America/New_York fixture geography, parsed/calculated every source,
and compared every complete monthly row to independent literals. First run
8913f1 exited 1 in 5.50 seconds: eight sources matched; Atlas's two sources
reported the expected missing hourly cost/version/calendar; Cedar's two sources
also failed because contractual_basis incorrectly contained evidence prose.
Corrected that field to the supported billable_units enum, preserving all original
evidence separately. Corrected run 1c8253 exited 0 in 6.82 seconds: all ten
non-Atlas sources matched every literal monthly revenue/cost; only atlas-staff
and atlas-extend remained unresolved. The command also asserted that the full
preflight rejects exactly those two, and original lifecycle labels are retained.
This successful diagnostic does not mean the twelve-source preflight passes.

Records now also expose preview_lifecycle with the original committed/planned/
draft labels, separate from canonical lifecycle. Read-only inspection of
api/app/gm/forecast.py confirms needs_review is eligible (line 108), receives
probability weighting in Expected and full weighting in Upside (lines 219-220),
and is separately surfaced as provisional (line 246). This is code inspection,
not persisted/browser forecast proof.
