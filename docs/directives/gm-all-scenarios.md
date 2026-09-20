# Directive: the GM engine handles every SOW shape, not the one I tested

From: Kanna Parimi, product owner. 19 September 2026. Extends `DealGate_Agent_Directive_GM_Correctness.md`. The $50k fixed-price case was one probe, not the requirement. The requirement is: any SOW we sign — project, services, staff aug, flex, managed service, assessment, placement, hybrid — produces a correct GM or an honest `incomplete`, never a wrong number and never an invented question.

## The design that makes "all scenarios" possible

Do not write an `if` chain per screen. Build the engine as **one calculation core plus a revenue rule and a cost rule per engagement type**, declared as data the core reads. A new SOW shape then means adding one rule pair and its fixtures, not touching the core. The core enforces the universal invariants below on every type.

### Revenue and cost rules by type

| Type | Revenue = | Cost = | Never do |
| --- | --- | --- | --- |
| Fixed price | The contract price (milestone schedule for phasing). Discounts/credits deducted first | Σ hours × cost rate + direct costs + contingency | Derive revenue from rates; require bill rates |
| Staff augmentation (1..n) | Σ billable hours (or days) × bill rate per line, over the term, net of holidays/leave per contract | Σ paid hours × loaded cost rate (paid ≠ billable: leave, bench, replacement obligations) | Assume billable = paid; drop a person's unpaid coverage cost |
| Time & materials | Forecast hours × rate card, **capped at the not-to-exceed if one exists**; show forecast and cap separately | Forecast hours × cost rate | Book the cap as revenue when forecast is lower |
| Managed service | Monthly fee × months + onboarding/setup fees + committed volume charges | Monthly team cost × months + tools/licenses + on-call + ramp months at full cost before full fee | Ignore ramp; spread onboarding cost as if it were margin |
| Assessment (2–6 wk) | Fixed fee | Working days × day cost per person + prep + reporting + travel | Scale cost from duration alone |
| Permanent placement | One-time fee | Recruiting effort + sourcing costs + refund reserve per the guarantee clause | Treat as staff aug |
| Hybrid (e.g. fixed build + T&M support + monthly service) | Each component under its own rule, from the SOW's own sections | Same, per component | Force one template over the whole document |

A SOW the classifier cannot fit (confidence below threshold, or contradictory signals) is presented to the user as component blocks to assign — "this section reads as fixed price, this as monthly service" — and each block runs its own rule. Unclassifiable is a UI conversation, never a guess inside the engine.

### Cross-cutting rules, applied to every type

- **Geography:** every cost line has a location; the engine splits US/India from the lines and tests each floor independently, combined shown as information. Fixed-fee mixed revenue uses the recorded allocation (default cost-weighted, Finance can override with basis). A line with no location → `incomplete`, named line.
- **FX:** non-USD SOWs convert at Finance's rate and date, stored on the GM version. Never a live rate at render time.
- **Discounts, credits, taxes:** discounts and credits reduce revenue before any test; sales taxes never enter revenue; pass-through expenses at zero margin sit outside GM per Finance policy and are shown separately.
- **Subcontractors:** their invoiced cost is delivery cost at the location where the work is performed.
- **Multi-year / escalations:** rate escalation clauses apply per period; the engine produces per-month exposure and full-term GM; a passing lifetime GM must not hide a failing year one.
- **Amendments / change orders / renewals:** a new package on the same SOW; the engine recomputes the amended whole plus the delta; prior approvals stay historical.
- **Boundaries:** floors compared at full precision (35.000% passes, 34.9999% fails); zero, negative or missing revenue → exception state, not a percentage; missing cost → `incomplete`, never zero.

### Universal invariants — encode as property tests that run against every type

For any input the engine accepts:

1. `gross_profit = revenue − cost` and `gm = gross_profit / revenue` exactly (Decimal), or the result is `incomplete`/`exception` — never NaN, never a number alongside missing inputs.
2. US result + India result reconcile to combined: revenues and costs sum, no line counted twice or dropped.
3. Removing any required input flips the result to `incomplete` naming that field; adding it back restores the identical number (determinism).
4. Scaling all revenues and costs by the same factor leaves GM% unchanged.
5. The engine never mutates its input and never asks a question — questions come only from validation reporting a truly absent field on the single staffing model.
6. Same inputs, same policy version, same output, forever (goldens are replayable).

## Golden fixture library — build all of these as files in `fixtures/sows/`, each with a hand-computed expected-results JSON

| # | Fixture | Expected (verify by hand before coding) |
| --- | --- | --- |
| 1 | Fixed $50k, US: 80h×$120 + 160h×$220 cost | Cost $44,800 · GM 10.4% · fails by 24.6 pts · min price $68,923.08 · CEO route |
| 2 | Fixed $145k mixed, $90k/$55k alloc, $65k/$30k cost | 27.78% / 45.45% / 34.48% · both fail (blueprint case) |
| 3 | Staff aug US ×2: 1,000h each, bill $150, cost $95 | Rev $300,000 · cost $190,000 · GM 36.67% · passes |
| 4 | Staff aug, single resource, 3 weeks unpaid-leave clause | Billable drops, paid cost doesn't · GM reflects it |
| 5 | T&M, cap $200k, forecast 1,400h × $140 bill / $85 cost | Rev $196,000 (forecast < cap) · GM 39.29% · cap shown separately |
| 6 | Managed service India: $18k/mo ×12, team $9.5k/mo | Rev $216,000 · cost $114,000 · GM 47.22% · fails 50% by 2.78 pts · min $228,000 |
| 7 | Assessment US 4-week: fee $38k, 2 people, prep+report+travel costed | GM from actual effort, not duration |
| 8 | Placement: fee $25k, recruiting cost $6k, 90-day refund clause | One-time model, refund reserve held |
| 9 | Hybrid: fixed build + 12-mo managed service in one SOW | Two components, each tested, combined informational |
| 10 | Discounted: any fixture with 10% discount clause | Revenue reduced before floor test |
| 11 | INR-denominated SOW | Converted at stored FX, GM in USD |
| 12 | Boundary: US exactly 35.000% / India 49.999% | Pass / fail at full precision |
| 13 | Missing: one line without cost rate; one without location | `incomplete`, names the line and field, no numbers presented as final |
| 14 | Amendment: fixture 3 + $40k scope addition at lower rate | New package, amended-whole GM + delta GM |
| 15 | Non-SOW (résumé) and malformed PDF | Rejected at document check, nothing created |

Fifteen fixtures, one expected-results file each, all in CI. When I test a shape you haven't got a fixture for and it breaks, the fix starts by adding that fixture.

## Definition of done

- All 15 goldens and the property tests pass in CI; the browser walkthrough works for fixtures 1, 3, 6 and 9 end to end (upload → auto-classified → grid pre-filled → GM correct → correct approval route) with screenshots in the report.
- `grep` gate from the intake directive still clean.
- A one-page `docs/gm-rules.md` generated from the rule table, so Finance can read what the engine does and confirm it — Finance sign-off on that page is part of done.
