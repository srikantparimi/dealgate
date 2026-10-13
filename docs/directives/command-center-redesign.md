Implement the approved Command Center redesign using the attached `DealGate_Command_Center_Redesign.html`.

The design is approved. Preserve its layout, visual hierarchy and interactions. There is ONE change to the approved design:

**Accounts & engagements must show only records backed by HubSpot deals at sales Stage 5 or above.**

### 1. Apply this eligibility rule precisely

- A row must be linked to an actual mirrored HubSpot deal.
- That deal must be in Stage 5 or a later stage within its own HubSpot pipeline.
- Resolve the Stage 5 threshold from the actual pipeline definitions and business configuration. HubSpot stage IDs are identifiers, not numbers to compare. Do not assume ordering is one-based or consistent across pipelines.
- This is the HubSpot SALES stage. A deal at sales Stage 3 does not qualify because its SOW has reached Signature or Handoff.
- Exclude unlinked local records, unknown stages and deals below the threshold. Linked SOW/project information can remain visible as engagement context.
- Preserve the established treatment of closed-won, closed-lost and archived records. Document that behavior; do not silently change it. If a pipeline has no identifiable Stage 5 threshold, flag the configuration gap instead of guessing.

Show a persistent scope label above the table:

**HubSpot deals · Stage 5 and above**

This is a mandatory section constraint. “Reset filters” must not remove it.

Apply the rule server-side to this section’s results, pagination totals, search and export. Preserve the existing row identity and prevent duplicate rows from SOW/project joins.

**Do not apply this threshold to the entire dashboard.** The action queue, business metrics, lifecycle overview, revenue outlook, capacity and activity retain their approved populations and scope rules.

### 2. Build the approved interface with real application data

Use the HTML as the visual and interaction specification—not as production data or business logic.

Implement:
- Compact header and BU, owner, financial-period, currency and role-focus controls.
- Visible, individually removable user filters.
- Ranked action queue with named accounts, responsible people, deadlines and meaningful actions.
- Business metrics with understandable definitions and supporting records.
- Commercial lifecycle overview with correct entity counts and conditional CEO review.
- Actual, remaining signed and potential revenue, including next-two-quarter and account/BU views.
- Staffing demand, allocations and capacity gaps.
- Accounts & engagements with the eligibility rule above.
- Recent changes, source freshness and operational failures.
- Responsive layouts, accessible controls, detail panels and preserved navigation context.

Use existing application services, permissions, calculation rules and workflows. Do not copy the prototype’s fictional accounts, sample rates, probabilities, staffing assumptions or simplified calculations into production.

Navigation previews in the HTML must become real links or in-place workspaces. No placeholder buttons or generic redirects to Pipeline.

### 3. Reconcile the data behind the interface

Inspect current origin/main, deployed versions and existing shared query services before implementation. The older audit checkpoint is historical; do not assume it is still current.

Use a separate worktree and feature branch. Preserve unrelated work.

- Reuse canonical populations and definitions across Command Center and owning pages.
- Distinguish deals, SOW packages and projects.
- Prevent double counting between actuals, remaining signed revenue and unsigned potential.
- Calculate aggregate GM from revenue and costs.
- Missing workforce supply or incomplete costs must remain unknown.
- Exclude voided/cancelled work from active operational queues according to existing policy.
- Keep current operational actions visible even when revenue starts outside the financial reporting period.
- Load sections independently, with useful empty, stale and error states.

Do not introduce a replacement financial engine or parallel approval workflow.

### 4. Verify the actual user behavior

Add focused connected coverage proving:

1. A HubSpot Stage 4 deal is excluded; Stage 5 and later qualify.
2. Sales-stage eligibility remains correct regardless of SOW approval stage.
3. Multiple pipelines, unknown stages and unlinked records behave explicitly.
4. Search, filters, pagination and CSV use the same eligible population.
5. Resetting filters preserves the Stage 5 minimum.
6. Other dashboard sections retain their original scope.
7. Cards and actions open the correct records and preserve Back navigation context.
8. Financial totals reconcile and missing data is not displayed as zero.

Run the relevant regression coverage. Avoid repeated broad test runs while diagnosing a narrow failure. Identify the failing boundary before changing code again.

### 5. Deliver a reviewable staging result

Deploy through the established staging process and verify that the running frontend and API contain the implementation.

Provide:
- Branch, worktree, commit and deployed version.
- Desktop/mobile screenshots and a short click-through.
- Evidence that Stage 5 eligibility works on the deployed page.
- Any unresolved data dependencies, clearly separated from completed UI work.

Update the existing durable handoff with the implementation, evidence and remaining work.

Completion means the approved design works with real data on staging. Stop for my acceptance before merging to main.