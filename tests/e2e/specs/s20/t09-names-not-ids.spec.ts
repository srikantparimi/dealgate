/**
 * T09 · exact-name assertions (S20 · W2 Session 3b).
 *
 * Per review:
 * > Names in headings, breadcrumbs, rows, owner/stage fields, search,
 * > and export. Known ids (11-digit deal, 10-digit stage, 8-char hash,
 * > UUID) never become labels.
 *
 * We assert on the pipeline list + deal detail + client detail
 * because those are the surfaces where L02/L04/L07 reported ids
 * leaking through as labels.
 *
 * Do NOT reject legitimate numeric names, amounts or dates — the
 * regexes below match the specific id shapes only:
 *  - 11-digit HubSpot deal id (e.g. 65211153545)
 *  - 10-digit HubSpot stage id (e.g. 1038193695)
 *  - UUID (36 chars with dashes)
 *
 * Note: some cells DO legitimately show the deal id as a subtitle
 * (e.g. "HS #65211153545") — those cells carry data-testid or come
 * inside a `text-text-secondary` container, and the check reads only
 * the primary label text (the h1 / first cell / stage cell).
 */
import { test, expect, type Page } from "@playwright/test";
import { authAsRole } from "../../fixtures/multi-role-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";

const RE_HS_DEAL_ID = /^\s*\d{11}\s*$/;
const RE_HS_STAGE_ID = /^\s*\d{10}\s*$/;
const RE_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function looksLikeRawId(text: string): boolean {
  const s = text.trim();
  return RE_HS_DEAL_ID.test(s) || RE_HS_STAGE_ID.test(s) || RE_UUID.test(s);
}

test.describe("T09 · names, not ids (S20)", () => {
  test.beforeEach(async ({ page }) => {
    await authAsRole(page, "system");
  });

  test("pipeline opportunity rows: deal column shows the dealname, not the stage id", async ({
    page,
  }) => {
    await page.goto(`${BASE}/pipeline`);
    // Ensure the opportunities view is visible; the default tab is Clients.
    await page.getByRole("tab", { name: /opportunities/i }).click();
    const table = page.getByTestId("opportunities-table");
    await expect(table).toBeVisible({ timeout: 15_000 });

    const rows = table.locator("tbody tr");
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);

    // First cell of each visible row is the deal name column. If it's a
    // raw id, that's the L04 regression the review specifically named.
    for (let i = 0; i < Math.min(rowCount, 10); i += 1) {
      const nameCell = rows.nth(i).locator("td").first();
      // Use `.textContent` because the cell contains BOTH the name and
      // a subtitle "HS #<id>"; the first text node is the visible label.
      const label = (await nameCell.locator(":scope > div > span, :scope > div").first().textContent()) ?? "";
      expect(
        looksLikeRawId(label),
        `row ${i} deal-name cell renders a raw id ("${label.trim()}") — expected a dealname`,
      ).toBeFalsy();
    }
  });

  test("pipeline opportunity rows: stage cell shows the label, not the numeric id", async ({
    page,
  }) => {
    await page.goto(`${BASE}/pipeline`);
    await page.getByRole("tab", { name: /opportunities/i }).click();
    const table = page.getByTestId("opportunities-table");
    await expect(table).toBeVisible();

    const rows = table.locator("tbody tr");
    const rowCount = await rows.count();
    for (let i = 0; i < Math.min(rowCount, 10); i += 1) {
      // Stage is the 3rd column in the opportunities table (Deal, Client, Stage).
      const stageCell = rows.nth(i).locator("td").nth(2);
      const text = (await stageCell.textContent()) ?? "";
      expect(
        looksLikeRawId(text),
        `row ${i} stage cell renders "${text.trim()}" — expected a stage label`,
      ).toBeFalsy();
    }
  });

  test("stage chips render labels, not raw stage ids", async ({ page }) => {
    await page.goto(`${BASE}/pipeline`);
    const strip = page.getByTestId("stage-strip");
    await expect(strip).toBeVisible({ timeout: 15_000 });
    const chips = strip.locator("button");
    const count = await chips.count();
    for (let i = 0; i < count; i += 1) {
      const label = (await chips.nth(i).locator("span").first().textContent()) ?? "";
      expect(
        looksLikeRawId(label),
        `chip ${i} renders raw id "${label.trim()}"`,
      ).toBeFalsy();
    }
  });

  test("deal detail page: heading shows dealname, not id", async ({ page }) => {
    // Land on Pipeline, click the first opportunity row, verify the deal
    // page heading shows a real dealname string.
    await page.goto(`${BASE}/pipeline`);
    await page.getByRole("tab", { name: /opportunities/i }).click();
    const firstRow = page.getByTestId("opportunities-table").locator("tbody tr").first();
    await firstRow.click();
    await page.waitForURL(/\/deals\/[0-9a-f-]{36}/, { timeout: 15_000 });

    const heading = page.getByTestId("deal-heading");
    await expect(heading).toBeVisible();
    const text = (await heading.textContent()) ?? "";
    expect(
      looksLikeRawId(text),
      `deal-detail heading renders a raw id "${text.trim()}"`,
    ).toBeFalsy();
    expect(text.length).toBeGreaterThan(2);
  });

  test("client detail page: heading shows client name, not UUID", async ({
    page,
  }) => {
    await page.goto(`${BASE}/pipeline`);
    // Clients tab is default.
    const firstClient = page.getByTestId("clients-table").locator("tbody tr").first();
    await expect(firstClient).toBeVisible({ timeout: 15_000 });
    await firstClient.click();
    await page.waitForURL(/\/clients\/[0-9a-f-]{36}/, { timeout: 15_000 });

    const heading = page.getByTestId("client-heading");
    await expect(heading).toBeVisible();
    const text = (await heading.textContent()) ?? "";
    expect(
      looksLikeRawId(text),
      `client-detail heading renders a raw id "${text.trim()}"`,
    ).toBeFalsy();
    expect(text.length).toBeGreaterThan(2);
  });
});
