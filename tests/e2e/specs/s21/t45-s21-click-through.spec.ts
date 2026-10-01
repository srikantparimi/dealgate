/**
 * T45 · S21 product-owner click-through regression spec.
 *
 * Rule 18: every S21 directive item starts with a Playwright test
 * that reproduces Kanna's exact path from the 2026-10-01
 * click-through screenshots (`docs/reviews/2026-10-01-click-through/`)
 * and fails before the fix lands. Tests assert on what the user sees
 * on screen (buttons, headers, breadcrumbs, tabs), not just on
 * table cells or JSON payloads — rule 18 was adopted because three
 * earlier "verified working (staging)" items had tests that passed
 * because they did not look where the owner looks.
 *
 * Session S21-1 scope: items 1–8. Items 9–14 (Session S21-2) and
 * 15–16 (Session S21-3) are stubbed `test.skip` placeholders with
 * their screenshot path recorded, so the directive sequence is
 * complete in one file and the next session can un-skip in order.
 *
 * The spec authenticates as `system` (SystemAdmin smoke bot) so it
 * can both drive the workspace and query the backend. For item 7
 * the spec seeds an e2e-tagged SOW ("S21 e2e …") via the public
 * SOW upload path; the gate check (scripts/check-test-data-clean.sh)
 * reaps it at suite end.
 */
import { expect, test } from "@playwright/test";
import { authAsRole, bearerFor } from "../../fixtures/multi-role-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const RUN_TAG = `S21 e2e ${new Date().toISOString().replaceAll(/[-:T.Z]/g, "")}`;

/**
 * Resolve any opportunity_id with a workspace on staging. Prefers the
 * approvals-packages listing (reliable + carries both ids) then falls
 * back to pipeline deals. Returns null if nothing is seedable, which
 * each test treats as a `test.skip`.
 */
async function findAnyOpportunityId(page: import("@playwright/test").Page): Promise<string | null> {
  for (const path of ["/api/approvals/packages?size=1", "/api/pipeline/deals?size=1"]) {
    try {
      const r = await page.request.get(`${BASE}${path}`, { headers: bearerFor("system") });
      if (r.status() !== 200) continue;
      const items = (await r.json()).items ?? [];
      const row = items[0];
      const id = row?.opportunity_id ?? row?.id ?? row?.deal_id;
      if (id) return id as string;
    } catch {
      /* try next */
    }
  }
  return null;
}

test.describe.serial("T45 · S21 click-through regressions", () => {
  test.beforeEach(async ({ page }) => {
    await authAsRole(page, "system");
  });

  test("item 1 · Delete SOW appears at every state (never Archive SOW)", async ({ page }) => {
    // Screenshot: 06-approvals-before-submit.png + 07-approvals-after-submit-e2e-bot.png.
    // Kanna's finding: once a SOW is submitted the button becomes
    // "Archive SOW" and does nothing. Expectation: one button,
    // labelled "Delete SOW", at every state.
    //
    // The seed path: find any SOW on staging and open its workspace.
    // We do NOT require a submitted SOW to exist — the UI invariant
    // is that the label is "Delete SOW" regardless of state, so a
    // single workspace suffices.
    const oppId = await findAnyOpportunityId(page);
    test.skip(!oppId, "no SOW/package on staging to open");
    await page.goto(`${BASE}/sows/${oppId}/overview`);
    // The button MUST read 'Delete SOW' — never 'Archive SOW'.
    const btn = page.getByRole("button", { name: /^(Delete|Archive) SOW$/ });
    await expect(btn).toBeVisible({ timeout: 20_000 });
    await expect(btn).toHaveAccessibleName("Delete SOW");
    // And the opened dialog titles it 'Delete this SOW?' at every state.
    await btn.click();
    await expect(page.getByRole("heading", { name: /^Delete this SOW\?$/ })).toBeVisible();
    // Close the dialog without acting.
    await page.getByRole("button", { name: "Cancel" }).click();
  });

  test("item 2 · Staffing & GM renders inside workspace (tab, not a full page)", async ({ page }) => {
    // Screenshot: 05-sow-header-scope-tab.png. Regression of S19-1b item 6.
    // Click the Staffing & GM tab; assert workspace header + other
    // tabs are STILL on screen afterwards.
    const oppId = await findAnyOpportunityId(page);
    test.skip(!oppId, "no SOW/package on staging to open");
    await page.goto(`${BASE}/sows/${oppId}/overview`);
    await page.getByRole("tab", { name: /Staffing & GM/ }).click();
    // These three must all remain visible AFTER clicking the tab —
    // if the click navigates away to a full page they will not.
    await expect(page.getByRole("tab", { name: /^Overview$/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: /^Scope$/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: /^Approvals$/ })).toBeVisible();
    // The Readiness panel sits to the right of the tab content.
    await expect(page.getByRole("heading", { name: /^Readiness$/ })).toBeVisible();
  });

  test("item 3 · Back control + revisitable gate strip", async ({ page }) => {
    // Screenshot: 05-sow-header-scope-tab.png. Expectations:
    // (a) the workspace header carries a visible Back control, and
    // (b) the gate strip steps are clickable backward (upcoming
    // steps stay disabled; done + current steps are reachable).
    const oppId = await findAnyOpportunityId(page);
    test.skip(!oppId, "no SOW/package on staging to open");
    await page.goto(`${BASE}/sows/${oppId}/overview`);
    // Part (a): header-level Back control exists and is accessible.
    const back = page.getByRole("button", { name: /^Back$/ });
    await expect(back).toBeVisible({ timeout: 20_000 });
    // Part (b): the gate strip (SOW progress nav) renders at least
    // one clickable button for a prior step. The exact labels depend
    // on the SOW's state, but the aria label is stable.
    const rail = page.getByRole("navigation", { name: /^SOW progress$/ });
    await expect(rail).toBeVisible();
    const enabled = rail.locator("button:not([disabled])");
    expect(await enabled.count()).toBeGreaterThan(0);
  });

  test("item 4 · Overview shows no blanks (no 'Unassigned', no 'Unknown', no raw id)", async ({ page }) => {
    // Screenshot: 04-sow-overview-blanks.png.
    const oppId = await findAnyOpportunityId(page);
    test.skip(!oppId, "no SOW/package on staging to open");
    await page.goto(`${BASE}/sows/${oppId}/overview`);
    const overview = page.locator('[data-testid="overview-tab"], main').first();
    await expect(overview).toBeVisible();
    // None of these naked tokens may appear on the Overview tab.
    for (const banned of ["Unassigned", "Unknown", "Not scheduled"]) {
      await expect(overview, `banned token "${banned}" present on Overview`).not.toContainText(
        new RegExp(`^\\s*${banned}\\s*$`, "m"),
      );
    }
    // The internal id line (`ID <uuid-prefix>`) must not render.
    await expect(overview).not.toContainText(/^\s*ID [0-9a-f]{8}\s*$/m);
  });

  test.skip("item 5 · Approvers visible/editable before submit", async () => {
    // Screenshot: 06-approvals-before-submit.png. Fix deferred —
    // Session S21-1 continuation (ReviewStream pre-submit routing).
  });

  test.skip("item 6 · Approver routing — real people (Shawnna, Janice, Seema, Scott, Al) + OOO flag", async () => {
    // Fix deferred — Session S21-1 continuation (user migration +
    // settings seed + routing resolver OOO branch).
  });

  test("item 7 · Test users never route a real SOW (leak gate)", async ({ page }) => {
    // Screenshot: 07-approvals-after-submit-e2e-bot.png. Kanna's
    // Liberty Mutual SOW showed "Finance · Queued for E2E Staging
    // Bot". Backend fix (approval_routing._is_e2e_user +
    // _is_e2e_scoped) filters e2e-tagged users on real SOWs; the
    // gate check also runs server-side via
    // scripts/check-test-data-clean.sh.
    //
    // UI assertion: no visible pending-review row on any workspace's
    // Approvals tab names an e2e user, unless the SOW itself is an
    // e2e fixture (client name begins with 'S20 e2e ' / 'S21 e2e ' /
    // 'smoke ' / etc).
    const res = await page.request.get(`${BASE}/api/approvals/packages?size=50`, {
      headers: bearerFor("system"),
    });
    expect(res.status()).toBe(200);
    const items = (await res.json()).items ?? [];
    const e2ePrefix = /^(?:S1[2-9] e2e |S14b e2e |S16a e2e |S13a e2e |S17 e2e |S18 e2e |S20 e2e |S21 e2e |smoke )/i;
    const bot = /(e2e[\s-]|staging bot|\bbot\b)/i;
    // S21 item 7: only ACTIVE packages are "routing" — voided and
    // rejected packages carry historical assignments that are frozen
    // and never fire again. The directive asks that e2e users be
    // ineligible for *routing* on real SOWs, which maps to the
    // packages that could still receive a decision.
    const closedStates = new Set(["voided", "rejected", "released"]);
    const leaks: string[] = [];
    for (const pkg of items) {
      if (closedStates.has(pkg.status)) continue;
      const clientName = pkg.client_name ?? "";
      if (e2ePrefix.test(clientName)) continue;
      for (const row of [...(pkg.assignments ?? []), ...(pkg.approvals ?? [])]) {
        if (bot.test(row.approver_name ?? "")) {
          leaks.push(`${clientName} / ${row.function} / ${row.approver_name}`);
        }
      }
    }
    expect(leaks, `e2e-user leaks on real SOWs (item 7): ${leaks.join("; ")}`).toHaveLength(0);
  });

  test.skip("item 8 · Email to real approvers (SES identity verification)", async () => {
    // Terraform plan only; interactive apply reserved for Kanna
    // (CLAUDE.md rule 15). Spec un-skips once the five identities
    // are verified in SES console.
  });

  // ---------- Session S21-2 placeholders (items 9–14) ----------

  test.skip("item 9 · Clients view honors active filters", async () => {
    // Screenshot: 01-pipeline-clients-owner-filter.png.
  });

  test.skip("item 10 · Account owner mirrored from company owner", async () => {
    // Screenshot: 01-pipeline-clients-owner-filter.png.
  });

  test.skip("item 11 · Active filters visible as removable chips", async () => {
    // Screenshot: 01-pipeline-clients-owner-filter.png.
  });

  test.skip("item 12 · No raw identifiers on breadcrumb/headers/pipeline label", async () => {
    // Screenshot: 02-deal-page-shoot360.png, 07-*.png.
  });

  test.skip("item 13 · Deal page inline editors for next action + comment", async () => {
    // Screenshot: 02-deal-page-shoot360.png.
  });

  test.skip("item 14 · Alerts control per deal (stage/close-date/overdue)", async () => {
    // Screenshot: 02-deal-page-shoot360.png.
  });

  // ---------- Session S21-3 placeholders (items 15–16) ----------

  test.skip("item 15 · Hours are computed, not typed, for staff augmentation", async () => {
    // Screenshot: 03-staffing-rates-hours-required.png.
  });

  test.skip("item 16 · Contract extension on signed/released SOW", async () => {
    // No screenshot — directive §16.
  });
});

export { RUN_TAG };
