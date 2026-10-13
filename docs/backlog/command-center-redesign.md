# Command Center redesign

## Product outcome

Replace the current executive-banner dashboard with the approved operational
Command Center: compact scope controls, ranked work, reconciled commercial and
delivery measures, lifecycle, revenue outlook, capacity, Stage-5-qualified
accounts and engagements, activity, and source health.

The approved interaction reference is
`docs/design/DealGate_Command_Center_Redesign.html`. It defines presentation and
interaction only; its sample records and calculations are never production
inputs.

## Stage 5 eligibility decision

For each non-archived HubSpot pipeline, order its non-archived mirrored stages
by `display_order`, then stable stage id. The fifth stage in that ordered
definition is the Stage 5 threshold. A deal qualifies when its mirrored stage
belongs to the same pipeline and is at or after that threshold. HubSpot stage
ids are opaque identifiers.

- Archived opportunities and archived mirrored stages are excluded.
- Closed-lost deals remain excluded from the active Accounts & engagements
  population, matching the Pipeline page's default active treatment.
- Closed-won deals at or after the threshold remain eligible so their linked
  engagement or project context can be shown.
- Unknown stages, unlinked local opportunities, and pipelines with fewer than
  five identifiable stages are excluded. The latter are returned as explicit
  configuration gaps.
- SOW governance status never affects this sales-stage test.

## Acceptance tests

1. Given an ordered pipeline with at least six stages, Stage 4 is excluded and
   Stage 5 and later are included.
2. Changing only a qualifying deal's SOW approval state does not change its
   eligibility.
3. Each pipeline resolves its own threshold; unknown stages, unlinked local
   rows and pipelines without a fifth stage are excluded and configuration
   gaps are exposed.
4. Search, BU/owner filters, pagination and CSV export operate on the same
   eligible population with one row per HubSpot deal.
5. Resetting user filters retains the visible `HubSpot deals · Stage 5 and
   above` constraint.
6. Action queue, pulse, lifecycle, revenue, capacity and activity retain their
   owning populations and are not restricted by Stage 5.
7. Cards and actions open the owning record or workspace and preserve the
   Command Center return URL and active scope.
8. Revenue and cost totals come from the established forecast/calculation
   services; missing workforce or costs render as unknown, never zero.
9. Each dashboard section has independent loading, empty, stale and error
   states; one failure does not blank healthy sections.
10. The desktop and mobile layouts remain readable and operable by keyboard,
    with named controls and a focus-contained detail drawer.

## Release boundary

Deploy the feature branch through the established staging workflow and stop
for product-owner click-through. Do not merge to `main` before explicit
acceptance.
