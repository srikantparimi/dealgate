Complete the Command Center's integration with the existing Forecast and Portfolio modules. Preserve the approved design and navigation. The remaining task is to make the page answer business questions using data already held by the application.

The reported baseline is 81 engagements, actuals through September, allocations, roll-offs and bench. Verify those populations against the current database and permissions; do not hardcode these numbers.

## 1. Establish the source of each metric

Before editing, produce a short mapping:

Displayed metric -> existing service/query -> included records -> reporting period -> calculation -> drill-down.

Trace why Forecast/Portfolio can display information that Command Center cannot. Check missing joins, legacy endpoints, incompatible filters, publication requirements and imported-versus-native record handling.

Reuse the authoritative services and calculations. A shared aggregation endpoint is acceptable; a separate Command Center financial model or duplicate engagement store is not.

Do not make users recreate or republish valid imported engagements merely to populate this page.

## 2. Put five actionable tiles first

Every tile must open the exact supporting population, preserving permissions, BU, owner, currency and reporting basis. Counts and amounts must reconcile with the destination.

- Revenue this month: full-month forecast, with current-month actual-to-date and its cutoff beside it. If October actuals are not loaded, say so and show the latest closed month separately. Include last-closed-month billing loss as supporting context.
- GM this month: calculate from revenue and costs for the same cost-covered engagements. Show "n of m engagements have costs" and the percentage of revenue covered. Distinguish confirmed costs from default-rate estimates.
- Signed backlog: remaining contracted revenue under effective signed terms, through SOW end dates and approved amendments. Exclude recognized revenue and unsupported extensions.
- Weighted pipeline: eligible open deal value x saved probability. Keep closed-won forecast gaps separate.
- People: billable people, bench and roll-offs within 60 days. Make each subcount independently clickable and identify whether it counts people, allocations or FTE.

Show comparison with the previous month on a consistent, labeled basis. GM changes use percentage points. If a historical snapshot is absent, say "Prior-month comparison not recorded"; do not reconstruct a false delta.

Remove generic "Unknown" labels. Use a specific explanation and a relevant fix, such as: "Costs available for 4 of 81 engagements -> Review cost setup."

Never replace missing information with zero.

## 3. Turn Needs attention into a financial action queue

Support these categories:

1. Closed-won deal with no linked engagement -> Create engagement from deal, using the existing feature.
2. Allocation rolling off within 60 days with no confirmed follow-on work -> Plan renewal or redeployment.
3. Engagement below its applicable GM floor -> Review margin and corrective action.
4. Forecast extending beyond the effective SOW end without renewal coverage -> Review contract coverage.
5. Billing loss above the configured threshold in the last closed month -> Investigate billing loss.
6. SOW awaiting the signed-in user's approval -> Review SOW.
7. Engagement missing applicable costs -> Complete cost setup.

Also detect SOWs ending within 60 days without a renewal item, even if their forecast correctly stops at the contract end.

Each row needs the account/engagement, specific problem, financial impact and period, accountable owner, and one meaningful action. Preserve Team / Assigned to me.

Default to descending comparable dollar impact; use urgency and the category order above as tie-breakers. Label contract value, revenue exposure and margin shortfall distinctly. Do not rank an entire multiyear contract as though it were a 60-day revenue loss.

Where impact cannot be calculated, show the missing input. Keep the action visible. Do not fabricate an amount, deadline or owner. Group related findings so overlapping risks are not added twice.

Creating an engagement must be idempotent and remove the gap after successful linkage.

## 4. Generate the operating brief from those same results

Exactly three useful statements:

- Largest quantified risk.
- Largest opportunity.
- Most consequential data blocker.

Include amount, affected population and a link to the underlying records. Generate these deterministically from the aggregates; AI wording is optional and must not invent facts.

Do not hardcode example values or missing-cost counts.

## 5. Populate the 3-6-month revenue outlook

Use mutually exclusive components:

- Committed: remaining signed revenue, stopping at effective contractual end dates.
- Expected renewal: proposed MSP/staff-augmentation continuation supported by a renewal item marked likely, with an amount, proposed term and explicit probability basis.
- Pipeline upside: weighted, unsigned opportunity revenue scheduled into the relevant months.

The toggles are cumulative: Committed; Committed + expected renewal; Committed + expected renewal + pipeline upside.

A renewal becoming signed must move into committed without duplication. Pipeline linked to an engagement or renewal must not appear again as upside.

Weighted deal value is not automatically monthly revenue. Where start dates or schedules are missing, show an "Unscheduled weighted pipeline" amount outside the monthly bars.

Flag forecast beyond a SOW end as uncovered. Do not silently delete the forecast or treat it as signed backlog.

## 6. Populate capacity by location and the lifecycle strip

Compare next-month required and available capacity in matching FTE or hours, using dated allocations, active employment, starts, exits, leave and calendars.

TBC rows are unfilled demand, not employees. Show bench, open seats and roll-offs by location. Keep headcount distinct from FTE and make skill/location mismatches visible.

Use the lifecycle: Pipeline -> SOW in approval -> Signed -> Engagement created -> Active -> Renewal due.

Each count opens its exact population. Label entity types and overlapping states; this is not an additive funnel.

Retain the previously approved restriction: Accounts & engagements shows only HubSpot-linked deals at sales Stage 5 or above. Do not apply that restriction to company financials, capacity or risk detection.

## 7. Add only the genuinely missing configuration

- Store likely/unlikely/unassessed on each renewal; Settings holds defaults and calculation rules. An open or unassessed renewal must not silently become likely.
- Add the billing-loss threshold with explicit units and scope, using the existing authoritative billing-loss definition. Do not substitute forecast-versus-actual variance.

Reuse existing location cost settings. Defaults must remain identifiable estimates and must not overwrite actual costs.

## 8. Prove the business result on staging

Use focused, connected checks:

- Every tile and its drill-down reconcile under the same scope.
- Imported Forecast/Portfolio engagements contribute correctly.
- September-only actuals do not become October actuals.
- Partial cost coverage produces correctly labeled GM.
- SOW-end boundaries, renewals and pipeline do not double count.
- Closed-won-to-engagement creation resolves the attention item.
- Part-time people and TBC demand produce correct capacity totals.
- All metrics respect authorization and currency rules.

Diagnose mismatches before rerunning broad suites. Do not spend cycles adjusting placeholders while authoritative data remains disconnected.

Deploy the integrated change and provide a compact receipt: metric, source, displayed result, supporting-list result, and screenshot on the exact deployed revision. Update the durable handoff with branch, worktree, commit and remaining blockers.

Completion means the page answers the five business questions with traceable figures and actionable exceptions. Stop for staging acceptance before merging.
