# Staffing & GM redesign — current-to-new coverage map

Implementation notes for the 2026-10-05 redesign directive
(`DealGate_Staffing_GM_Redesign_Prompt.txt`). The prototype HTML is a
visual reference with demonstration data only; nothing here takes a
value, rate, location, ratio or target from it.

## Where the tab actually lives

`SowWorkspace` renders `StaffingGmTab`, which renders
`CommercialModelEditor` whenever the GM model carries a commercial
profile/inputs or no GM model exists yet for an uploaded SOW (the common
path). The legacy resource-line grid remains for pre-commercial GM
models and is unchanged by this redesign. The single readiness panel is
the workspace `<aside>` in `SowWorkspace.tsx` — the redesigned tab adds
no second checklist.

## Seven registered pricing models (real registry, `api/app/gm/commercial.py`)

| key (`PRICING_PROFILES`) | public label (`PROFILE_LABELS`) | required_fields (actual schema keys) | editor component |
|---|---|---|---|
| `fixed_assignment` | Fixed assignment | `total_fee`, `allocations`, `allocation_basis` | `PricingFields` (fee branch) + monthly allocations |
| `recurring_msp` | Recurring MSP | `monthly_fee` (as `fees[]` rows), `proration`, `included_scope` | `PricingFields` MSP branch + `MspAdjustmentsFields` (`adjustments[]`, `usage[]`) |
| `calendar_staff_aug` | Calendar staff augmentation | `assignments` (component `staffing[]`), `rate_basis` (`pricing.rates[]`: basis/rate/version/hours_per_day/proration) | `CalendarFields` |
| `tm` | Time & materials | `rate`, `unit`, `estimate` (`estimates[]`), `quantity_basis` (+ `approved_usage[]`, `cap`, `minimum`, `limit_allocation_basis`, `minor_unit`, `calendar_estimates`) | `PricingFields` T&M branch |
| `milestone` | Milestone | `milestones[]` (`planned_date`, `location`, `amount`, `acceptance_conditions`, read-only `approved_invoice_ref`/`recognized_revenue_ref`) | `PricingFields` milestone branch |
| `unit` | Unit / story point | `rate`, `unit`, `quantity` (`quantities[]`), `contractual_basis` | `PricingFields` unit branch |
| `hybrid` | Hybrid | `components[]` (child components), `shared_cost_allocations[]` (+ `allocation_basis`, `minor_unit`, `fx_rates[]`) | `HybridFields` (recurses into the above) |

No field dropped; model-specific editors are reused verbatim inside the
new section layout. Fields whose semantics the attachments do not
explain (e.g. `limit_allocation_basis`, `fx_rates[].as_of`) stay where
they are, grouped under the section's Advanced area, labels unchanged.

## Field/action map (directive §3 → implementation)

Section 1 · Contract & pricing
- Pricing profile → "Engagement pricing model" select (real registry labels; confirm-replace flow retained).
- Workstream → unchanged input.
- `service_start`/`service_end` → "Contract dates", with stated duration shown beside when derivable; unknown stays unknown.
- Timezone / currency → "Contract timezone" / "Contract currency", editable.
- Billing cadence → "Billing schedule" (free text retained; empty = Unconfirmed).
- Cost basis → under "Advanced pricing details".
- `source_evidence` → "Source document & evidence" collapsible drawer (existing textarea, SOW version named).
- `pricing.total_fee` → "Contract fee" (currency-formatted summary; zero vs blank/unknown preserved — input remains the exact Decimal string).
- `allocation_basis` → "Revenue allocation method"; also shown beside monthly planning (section 3).
- `minor_unit` → Advanced → "Rounding precision (0.01 = cents)".
- Advisor fee/duration → read the canonical contract fee and dates; no independent duplicate state (PlanTeam fee field removed in favor of the canonical one).

Section 2 · Team & calendars
- Target GM → "Target margin (%)" with the configured policy floors displayed separately (from `/delivery-model/commercial/profiles` policy — never invented).
- Required FTE → "Estimated scope effort (FTE)" with source/assumptions, editable draft.
- Onshore minimum → "Minimum onshore effort (FTE)", optional, defaults to none (no design-imposed minimum).
- Advise staffing → "Suggest a team"; Apply mix → "Review & apply proposal" with compare + undo.
- Suggested mix/gaps → AI proposal card: demand vs budget-supported capacity kept separate; explicit blocked/unknown states.
- `staffing[]` rows: role → Role; `location` → "Delivery location"; `quantity` → "Number of people"; `allocation` → "Allocation per person (%)" with derived FTE shown (`people × allocation`); `start`/`end` → "Role dates" defaulting from contract dates with row overrides retained; timezone/currency → role Advanced; `cost_rate` + `cost_rate_basis` → "Delivery cost rate" with units; `cost_version` → role details; `bill_rate`/`rate_version` → "Client billing rate" + source (reference-only note for fixed-fee models); calendar → "Working calendar" (versions, holidays, confirmation retained); add/remove → Add role / row delete; Duplicate added.

Section 3 · Monthly plan & expenses
- `pricing.allocations[]` (fixed_assignment) → Month / "Revenue geography" / "Share of contract (%)" (percent display, fraction schema preserved; derived currency amount shown; conservation + 100% validation via existing `AllocationSummary`, extended).
- `costs[]` (PeriodCost) → "Other delivery expenses" (every field retained).
- Monthly schedule preview → existing server `Schedule` render (revenue, cost, calendar hours detail).

Section 4 · Review & save
- `costs_confirmed` → explicit human attestation checkbox (never pre-checked by AI — proposal/apply never set it).
- Change reason → "Version note" (required for save, as today).
- Preview → existing `/commercial/preview`; result labeled provisional ("Unsaved preview") exactly as the existing calculationState machine does.
- Save version → existing POST versions route (permissions, optimistic concurrency via `expected_gm_model_id`, audit unchanged).
- History → GM version chip in the workspace header; full saved-version browser remains a listed gap (no existing commercial-version history UI; not invented here).
- Submit/complete-scope → the existing workspace CTA, untouched.

## Percent and FTE display

`fractionToPercent`/`percentToFraction` in `format.ts` shift the decimal
point textually (no floats touch stored values); schema keeps fractions.
FTE summary = people × allocation, display-only arithmetic labeled as
such; all money stays server-side Decimal.

## AI-first staffing (directive §5)

- `bedrock_team_estimate` schema extended: per-role `skills`, `seniority`,
  `phase`, `people`, `allocation`, `basis` (`stated`|`inferred`); top-level
  `unknowns[]` and `coverage`. Estimator never sees fee/rates (demand is
  independent of budget by construction).
- `staffing_advice.advise` no longer 422s on missing fee/duration: the
  scope estimate always returns; affordability becomes
  `affordability: "calculated" | "blocked"` with `blocked_reasons[]`.
  Zero revenue, missing rates and no-feasible-mix are explicit states.
- No onshore minimum unless the user supplies one (`min_onshore_fte`
  defaults 0; all-onshore and all-offshore candidate mixes are solver
  grid members already).
- Auto-run once for an empty draft; regeneration is a deliberate button;
  suggestions never auto-apply; apply offers undo and preserves manual
  rows unless replacement is accepted; `costs_confirmed` untouched.
- Resolution actions on a gap: increase fee / reduce scope / change term /
  GM exception — each a proposal routed through existing editing + the
  existing approval workflow; the exception path is the existing CEO
  exception and is explicitly labeled as not curing a delivery gap.

## Known genuine gaps (listed, not hidden)

- Draft persistence across full page reload: drafts survive section and
  SOW-tab navigation via an in-memory draft cache (tested); a browser
  reload still loses unsaved edits (same as before the redesign). No
  server draft table exists and browser storage of SOW financials is
  not approved.
- Saved commercial version history browser: only the current version is
  viewable; prior versions are immutable rows without a list UI.
- Locations remain the engine's configured `US`/`India`; onshore/offshore
  labels in advice are relative labels over these configured locations.
