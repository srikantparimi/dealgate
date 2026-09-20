# How the gross margin is calculated

Generated from `api/app/gm/engine.py` — do not edit by hand. Run
`python api/scripts_gen_gm_rules.py` after changing a rule.

This page exists so Finance can read what the engine does and confirm it. The
table below is the same data the engine reads at run time; there is no second
description of the rules that could drift from the code.

## The floors

| Geography | Floor |
| --- | --- |
| US | 35% |
| India | 50% |

Each geography is tested against its own floor, independently. The combined
figure is shown for information and is never the thing that passes or fails —
a healthy US component must not carry a failing India one over the line.

Floors are compared **unrounded**. 35.000% passes; 34.9999% does not. Rounding
to two places first would make both read "35.00%" and erase the distinction.

## What the engine will not do

- It will not present a number alongside a missing input. A missing cost rate
  makes the result **incomplete** and names the line; it is never read as zero
  cost, which would inflate the margin and pass a floor the engagement fails.
- It will not report a percentage when revenue is zero, negative or absent.
  That is an **exception** state: `0.0%` reads as a real and very bad margin,
  and "there is nothing to divide by" is a different statement.
- It will not guess at an engagement type it has no rule for.
- It will not ask a question. Where a field is absent it says which field, on
  which line. Deciding what to do about that belongs to the screen.

## Rules by engagement type

### Assessment

`assessment`

| | |
| --- | --- |
| **Revenue** | The fixed fee, discounts deducted first. |
| **Cost** | Working days × day cost per person, plus preparation, reporting and travel as direct costs. |
| **Never** | Scale cost from the elapsed duration. A four-week assessment is not four weeks of everybody's time. |

### Fixed price

`fixed_price`

| | |
| --- | --- |
| **Revenue** | The contract price, with discounts and credits deducted first. Split across geographies by the recorded allocation, or by cost-weighted effort when none is recorded. |
| **Cost** | Σ paid hours × cost rate, plus direct costs, plus contingency. |
| **Never** | Derive revenue from bill rates, or require a bill rate. On a fixed fee the revenue is settled and nobody bills by the hour. |

### Managed service

`managed_service`

| | |
| --- | --- |
| **Revenue** | Monthly fee × months, plus onboarding and setup fees, plus committed volume charges. |
| **Cost** | Monthly team cost × months, plus tools and licences, plus on-call, plus ramp months at full cost before the full fee. |
| **Never** | Ignore ramp, or spread onboarding cost as if it were margin. |

### Permanent placement

`permanent_placement`

| | |
| --- | --- |
| **Revenue** | The one-time placement fee. |
| **Cost** | Recruiting effort and sourcing costs, plus a refund reserve set by the guarantee clause. |
| **Never** | Treat it as staff augmentation. There are no billable hours. |

### Single resource

`single_resource`

| | |
| --- | --- |
| **Revenue** | Staff augmentation with one line. |
| **Cost** | As staff augmentation. |
| **Never** | Treat it as a fixed fee because there is only one person. |

### Staff augmentation

`staff_aug`

| | |
| --- | --- |
| **Revenue** | Σ billable hours × bill rate per line, over the term. |
| **Cost** | Σ PAID hours × loaded cost rate. Paid is not billable: leave, bench and replacement obligations are paid and not billed. |
| **Never** | Assume billable equals paid, or drop a person's unpaid coverage cost. Both overstate the margin. |

### Time and materials

`tm`

| | |
| --- | --- |
| **Revenue** | Forecast hours × rate card, capped at the not-to-exceed where one exists. Forecast and cap are reported separately. |
| **Cost** | Forecast hours × cost rate, plus direct costs. |
| **Never** | Book the cap as revenue when the forecast is lower. The cap is a ceiling, not an amount anyone has agreed to pay. |

## Cross-cutting rules

- **Geography.** Every cost line carries a location. Fixed-fee revenue is
  split by the recorded allocation where Finance has set one, otherwise by
  cost-weighted effort. A line with no location makes the result incomplete
  and is named.
- **FX.** A non-USD SOW is converted at the rate and date Finance published,
  stored on the GM version. Never a live rate at render time — that would
  make the same SOW show a different margin tomorrow.
- **Discounts and credits.** Deducted from revenue before any floor test.
  Testing the list price passes the engagement on money we never charged.
- **Pass-through expenses.** Held outside the margin at zero, and shown
  separately.
- **Subcontractors.** Their invoiced cost is delivery cost, at the location
  where the work is performed.
- **Contingency.** Applied to cost where a percentage is set.
- **Amendments and change orders.** A new package on the same SOW. The engine
  reports the amended whole *and* the delta, because a whole that still looks
  acceptable can hide an addition priced well below the floor. Prior
  approvals stay historical.
- **Hybrid SOWs.** Each component runs under its own rule and is tested
  against its own floor. Forcing one template over a document containing a
  fixed build and a monthly service produces a number that describes neither.

## Verification

Every rule above is covered by a golden fixture in `fixtures/sows/`, each with
an expected-results file computed by hand and verified independently before
the engine existed. The universal invariants — exact Decimal arithmetic,
US/India reconciliation, determinism, scale-invariance of the margin, and
non-mutation of inputs — are asserted as property tests over generated inputs
across every type in the table.
