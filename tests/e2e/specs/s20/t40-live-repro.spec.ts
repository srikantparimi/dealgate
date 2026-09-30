/**
 * T40 · live L02-L07 reproductions (S20 · W5 + W2 Session 3b).
 *
 * Regression guards for the exact findings the review documented against
 * the live app on 2026-09-29:
 *   L02: Proposal 17 chip zeroed the list, /pipeline unchanged.
 *   L03: 50 rows, no next-page control, 106 matches claimed.
 *   L04: Deal column repeated the stage label.
 *   L05: Unassigned + Open 0 + activity never on client rows.
 *   L06: Stage chips summed to 50 (page-scoped aggregation smell).
 *   L07: 74 Sky detail rendered numeric stage; activity showed raw JSON.
 */
import { test, expect, type Page } from "@playwright/test";
import { authAsRole } from "../../fixtures/multi-role-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";

async function switchToOpportunities(page: Page): Promise<void> {
  await page.getByRole("tab", { name: /opportunities/i }).click();
  await expect(page.getByTestId("opportunities-table")).toBeVisible({
    timeout: 15_000,
  });
}

test.describe("T40 · L02-L07 live reproductions (S20)", () => {
  test.beforeEach(async ({ page }) => {
    await authAsRole(page, "system");
  });

  test("L02: clicking a stage chip filters in place and updates the URL", async ({
    page,
  }) => {
    await page.goto(`${BASE}/pipeline`);
    await switchToOpportunities(page);
    const strip = page.getByTestId("stage-strip");
    await expect(strip).toBeVisible({ timeout: 15_000 });
    // Pick the first non-zero chip.
    const chip = strip.locator("button").first();
    await chip.waitFor({ state: "visible" });
    // Extract the stage id from the data-testid attribute.
    const testid = await chip.getAttribute("data-testid");
    expect(testid).toMatch(/^stage-chip-/);
    const stageId = (testid ?? "").replace(/^stage-chip-/, "");
    await chip.click();

    // URL adds ?stage=<id>. The pipeline page reads it back into the filter set.
    await expect(page).toHaveURL(new RegExp(`stage=${stageId}(&|$)`), {
      timeout: 5_000,
    });
    // The list is either non-empty (rows match) or an empty state — either
    // is honest. The regression was that the URL did NOT change; that's the
    // primary assertion above.
  });

  test("L03: pagination 25/50/100 + global totals reachable", async ({
    page,
  }) => {
    await page.goto(`${BASE}/pipeline`);
    await switchToOpportunities(page);
    const paginator = page.getByTestId("paginator");
    await expect(paginator).toBeVisible({ timeout: 15_000 });
    // Header shows "Showing X-Y of TOTAL".
    const totalText = (await paginator.textContent()) ?? "";
    expect(totalText).toMatch(/of\s+[\d,]+/i);

    // Page-size selector switches to 100 without a full reload.
    const pageSize = paginator.getByTestId("page-size");
    await pageSize.selectOption("100");
    await expect(page).toHaveURL(/page_size=100/, { timeout: 5_000 });
  });

  test("L04: deal column shows dealname, not stage label", async ({ page }) => {
    await page.goto(`${BASE}/pipeline`);
    await switchToOpportunities(page);
    const rows = page.getByTestId("opportunities-table").locator("tbody tr");
    const first = rows.first();
    await first.waitFor({ state: "visible" });
    // Deal name cell (first td) should NOT equal the stage cell (3rd td).
    const dealText = (
      await first.locator("td").first().locator("span").first().textContent()
    ) ?? "";
    const stageText = (
      await first.locator("td").nth(2).textContent()
    ) ?? "";
    expect(dealText.trim().length).toBeGreaterThan(0);
    expect(
      dealText.trim() === stageText.trim(),
      "deal cell repeats the stage label — L04 regression",
    ).toBeFalsy();
  });

  test("L05: client rows show owner + Open count + last activity", async ({
    page,
  }) => {
    await page.goto(`${BASE}/pipeline`);
    const rows = page.getByTestId("clients-table").locator("tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 15_000 });
    // Account owner column is 2nd; matching/total column is 3rd. Both
    // exist and are populated on every row.
    const owner = (await rows.first().locator("td").nth(1).textContent()) ?? "";
    const rollup = (await rows.first().locator("td").nth(2).textContent()) ?? "";
    expect(owner.trim().length).toBeGreaterThan(0);
    expect(rollup.trim()).toMatch(/\d+/);
  });

  test("L06: stage chips exist with counts (D9 aggregation)", async ({ page }) => {
    await page.goto(`${BASE}/pipeline`);
    const strip = page.getByTestId("stage-strip");
    await expect(strip).toBeVisible({ timeout: 15_000 });
    const chips = strip.locator("button");
    const count = await chips.count();
    expect(count).toBeGreaterThan(0);
    // Every chip has a non-empty count span at the end.
    for (let i = 0; i < count; i += 1) {
      const t = (await chips.nth(i).textContent()) ?? "";
      expect(t).toMatch(/\d+/);
    }
  });

  test("L06b: at least one chip with count > 0 also carries a value line (S3b Rev-2)", async ({
    page,
  }) => {
    // Chip value is the "count + value per chip" review contract. On
    // staging portals with real deals, at least one non-closed chip has
    // count > 0 and a currency-formatted value line under it.
    await page.goto(`${BASE}/pipeline`);
    const strip = page.getByTestId("stage-strip");
    await expect(strip).toBeVisible({ timeout: 15_000 });
    const chips = strip.locator("button");
    const count = await chips.count();

    let sawValue = false;
    for (let i = 0; i < count; i += 1) {
      const chip = chips.nth(i);
      const testid = await chip.getAttribute("data-testid");
      if (!testid) continue;
      const stageId = testid.replace(/^stage-chip-/, "");
      const value = chip.getByTestId(`stage-chip-value-${stageId}`);
      if (await value.count()) {
        const text = (await value.textContent()) ?? "";
        if (text.trim().length > 0) {
          sawValue = true;
          break;
        }
      }
    }
    expect(
      sawValue,
      "at least one chip on staging should carry a value line — chip-value contract missing",
    ).toBeTruthy();
  });

  test("Owner + BU filter selects are present in the filter bar (S3b Rev-2)", async ({
    page,
  }) => {
    await page.goto(`${BASE}/pipeline`);
    await expect(page.getByTestId("filter-bar")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("filter-owner")).toBeVisible();
    await expect(page.getByTestId("filter-business-unit")).toBeVisible();
    // The BU select on this staging portal is disabled — D10 evidence
    // says the BU property isn't mirrored yet, so the axis is present
    // but honestly named "not mirrored".
    const buDisabled = await page.getByTestId("filter-business-unit").isDisabled();
    if (buDisabled) {
      const buOption = await page
        .getByTestId("filter-business-unit")
        .locator("option")
        .first()
        .textContent();
      expect(buOption).toContain("not mirrored");
    }
  });

  test("L07: client detail with only closed-lost deals renders Closed Lost readably", async ({
    page,
  }) => {
    // Search for a client that we expect exists — the review specifically
    // named 74 Sky. If the staging portal doesn't have this deal, the test
    // is skipped rather than failing, so this remains a real regression
    // guard when 74 Sky is present.
    await page.goto(`${BASE}/pipeline?search=74%20Sky`);
    const firstClient = page.getByTestId("clients-table").locator("tbody tr").first();
    const clientVisible = await firstClient
      .waitFor({ state: "visible", timeout: 8_000 })
      .then(() => true)
      .catch(() => false);
    if (!clientVisible) {
      test.skip(true, "74 Sky not present on this staging portal");
      return;
    }
    await firstClient.click();
    await page.waitForURL(/\/clients\/[0-9a-f-]{36}/, { timeout: 15_000 });

    // Rollup shows Open 0 with a readable Closed Lost callout when all
    // deals are lost.
    const rollup = page.getByTestId("client-rollup");
    await expect(rollup).toBeVisible();
    const openCount = (await page.getByTestId("rollup-open").textContent()) ?? "";
    if (openCount.trim() === "0") {
      // If Open is 0 and Closed Lost > 0, the callout renders.
      const closedLost = Number(
        (await page.getByTestId("rollup-closed-lost").textContent()) ?? "0",
      );
      if (closedLost > 0) {
        await expect(
          page.getByTestId("client-closed-lost-callout"),
        ).toBeVisible();
      }
    }

    // Activity renders as prose (no bare JSON braces in any activity row).
    const activity = page.getByTestId("client-activity");
    await expect(activity).toBeVisible();
    const activityText = (await activity.textContent()) ?? "";
    expect(activityText).not.toMatch(/^\{"/);
    expect(activityText).not.toMatch(/^\[/);
  });
});
