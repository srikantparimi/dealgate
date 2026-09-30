/**
 * T01 · sidebar navigation (S20 · W5).
 *
 * Per review: "Click every sidebar item, KPI and stage chip. Each has
 * its specified destination/filter behavior; no generic /pipeline
 * fallback."
 *
 * The v2 shell (`web/src/ui-v2/PrimaryNavigation.tsx`) declares five
 * groups: Workspace, Growth, Commitments, Operations, Administration.
 * The permission-gated items live behind `requireAny`; the smoke bot
 * used by the SystemAdmin role slot passes every gate, so every item
 * in `NAV_GROUPS` should be visible and navigate to its stated route.
 *
 * Assertions per item:
 *  1. clicking the link changes `window.location.pathname` to the
 *     link's `to`;
 *  2. the resulting URL is NOT `/pipeline` unless the item's own `to`
 *     is `/pipeline` (regression on L02 — Proposal-17 kept `/pipeline`
 *     but produced zero rows);
 *  3. the destination page renders its own recognizable header/heading
 *     within 15s, not a generic empty state.
 *
 * KPI + stage-chip clicks (part of T01) live in the Pipeline page and
 * depend on W2 landing the URL-state filter bar. Those assertions are
 * grouped in `stage-chips.spec.ts` (skeleton below in this file too,
 * marked skip until W2 lands).
 */
import { test, expect, type Page } from "@playwright/test";
import { authAsRole } from "../../fixtures/multi-role-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";

// One row per item in web/src/ui-v2/PrimaryNavigation.tsx NAV_GROUPS.
// If a group's `requireAny` gates it, the row lists the required role
// and the test picks a role slot that satisfies it. The smoke-bot
// SystemAdmin is a member of every governance group, so `system` covers
// every item; the role split matters more once the pool is partitioned.
const NAV_ITEMS: Array<{
  to: string;
  label: RegExp;
  destinationMarker: RegExp;
}> = [
  // /command's h1 renders "Command center. Every commitment in view." —
  // Command-center-specific identity per S20 Session 3b directive, not the
  // generic banner default that any page might reuse.
  { to: "/command", label: /command center/i, destinationMarker: /command center/i },
  { to: "/work", label: /my work/i, destinationMarker: /my work/i },
  { to: "/pipeline", label: /pipeline clients/i, destinationMarker: /pipeline|opportunities|clients/i },
  // Sidebar labels the slot "AI discovery"; the page's PageHeader title is
  // "AI adviser" (the feature name). Both should match a common word.
  { to: "/discovery", label: /ai discovery/i, destinationMarker: /adviser|discovery/i },
  { to: "/agreements", label: /nda & msa|agreements/i, destinationMarker: /nda|msa|agreements/i },
  { to: "/sows", label: /sow approvals/i, destinationMarker: /sow|approvals/i },
  { to: "/sows/new", label: /new sow studio/i, destinationMarker: /new sow|upload sow|studio/i },
  { to: "/projects", label: /^projects$/i, destinationMarker: /projects/i },
  { to: "/renewals", label: /^renewals$/i, destinationMarker: /renewals/i },
  { to: "/handoffs", label: /signed handoff/i, destinationMarker: /handoff/i },
  { to: "/reports", label: /reporting/i, destinationMarker: /report/i },
  { to: "/settings", label: /^settings$/i, destinationMarker: /settings|integrations/i },
];

async function clickNav(page: Page, label: RegExp): Promise<void> {
  const link = page.getByRole("link", { name: label }).first();
  await link.waitFor({ state: "visible", timeout: 15_000 });
  await link.click();
}

test.describe("T01 · sidebar navigation (S20)", () => {
  test.beforeEach(async ({ page }) => {
    // SystemAdmin smoke bot sees every gated item.
    await authAsRole(page, "system");
  });

  test("each NAV_GROUPS item lands on its own route", async ({ page }) => {
    await page.goto(`${BASE}/command`);
    // Wait for the shell to finish rendering the primary nav.
    await page.getByRole("navigation", { name: /primary/i }).first().waitFor({
      state: "visible",
      timeout: 30_000,
    });

    for (const item of NAV_ITEMS) {
      await test.step(`click "${item.label.source}" → ${item.to}`, async () => {
        await clickNav(page, item.label);
        // 1. URL matches the declared target (not the /pipeline fallback).
        await expect(page).toHaveURL(
          new RegExp(`${item.to.replace(/\//g, "\\/")}(\\/|$|\\?)`),
          { timeout: 15_000 },
        );
        // 2. Regression guard for L02: if the target was NOT /pipeline,
        //    the URL must not have degraded to /pipeline.
        if (item.to !== "/pipeline") {
          expect(page.url()).not.toMatch(/\/pipeline(\/|$|\?)/);
        }
        // 3. Destination renders its own heading/marker within timeout.
        await expect(
          page.locator("h1, h2").filter({ hasText: item.destinationMarker }).first(),
        ).toBeVisible({ timeout: 15_000 });
      });
    }
  });
});

test.describe("T01b · KPI + stage-chip navigation (depends on W2)", () => {
  // Skipped skeleton — W2 owns the pipeline page with URL-state filters.
  // When W2 lands, unskip and assert that each metric card + stage chip
  // navigates to a URL that carries the filter state (open_closed=..,
  // stage=.., attention=..) and that the resulting list reconciles with
  // the chip's declared count.
  test.skip("clicking Proposal 17 chip applies stage filter and updates URL", async () => {
    // 1. Land on /pipeline, wait for stage chips.
    // 2. Click the chip whose label is 'Proposal 17' (was L02's failing case).
    // 3. Assert URL now contains `stage=1038193692` (id-based, not label).
    // 4. Assert the list length reconciles to the chip's count (T02 linkage).
    // 5. Reload — chip stays selected, filter persists.
  });

  test.skip("clicking KPI card on Command center opens the filtered list", async () => {
    // 1. Land on /command, capture each KPI's declared count.
    // 2. Click "Open opportunities" — /pipeline?open_closed=open.
    // 3. Assert /pipeline row total matches KPI count (T39 report parity).
  });
});
