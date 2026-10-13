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
- Closed-won deals at or after the threshold remain eligible only when the win
  falls inside the selected financial period or a non-closed engagement
  overlaps that period. Historical wins without current delivery context are
  excluded; linked current delivery context remains visible.
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
11. A historical Closed Won deal without current delivery context is absent
    from the table, attention queue, lifecycle pipeline count and recent
    activity. A current-period win remains actionable, and an older win with
    an active in-period engagement remains visible as delivery context.

## Release boundary

Deploy the feature branch through the established staging workflow and stop
for product-owner click-through. Do not merge to `main` before explicit
acceptance.

## Execution decision

The product owner authorized uninterrupted implementation and verification for
this slice on 2026-10-13 ("don't stop until everything is implemented and all
testing is passed and background integration is also fully completed"). This
replaces the default 60-minute stopping point for this Command Center branch;
durable checkpoints continue throughout the work. It does not replace the
Terraform approval rule, staging click-through, or prohibition on merging to
`main` before explicit acceptance.
