/**
 * S19 slice 1 · J7 screenshots (pre-J6 subset).
 *
 * J6 needs a freshly-authored HubSpot deal, which the PO can't produce
 * on their own account today; the deal-create path is deferred to
 * tomorrow's team session. This spec captures every J7 panel that does
 * NOT depend on the newly-webhook-landed deal, against the live
 * staging deploy of feat/s19-pipeline-1.
 *
 * Emits the following PNGs into docs/reports/s19-1/:
 *   - clients-view.png       — /pipeline · Clients tab
 *   - opportunities-view.png — /pipeline · Opportunities tab
 *   - summary-bar.png        — cross-currency summary bar
 *   - stage-strip.png        — per-stage chips
 *   - sync-banner.png        — synced-N-min-ago pill
 *   - expanded-client.png    — /clients/:id workspace (row-expand
 *     itself is slice-2; row-click on /pipeline navigates here today)
 *
 * The J6 spec (25-*) picks up the webhook-created deal screenshot
 * tomorrow.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { test, expect } from "@playwright/test";
import { authStaging } from "../fixtures/staging-auth";

const REPORTS = path.resolve(__dirname, "..", "..", "..", "docs", "reports");
const S19_DIR = path.join(REPORTS, "s19-1");
fs.mkdirSync(S19_DIR, { recursive: true });

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";

test.describe("S19 slice 1 — J7 pre-deal screenshots", () => {
  test.setTimeout(2 * 60 * 1000);

  test("capture Pipeline + Command centre panels", async ({ page }) => {
    await authStaging(page, BASE);
    await page.goto(`${BASE}/pipeline`);
    await expect(
      page.getByRole("heading", { name: /^Pipeline$/ }),
    ).toBeVisible();

    // Clients view (default tab). Full-page + panel screenshots.
    await page.getByRole("tab", { name: /^Clients/ }).click();
    await expect(page.getByTestId("clients-table")).toBeVisible();
    await page.screenshot({
      path: path.join(S19_DIR, "clients-view.png"),
      fullPage: true,
    });
    await page.getByTestId("summary-bar").screenshot({
      path: path.join(S19_DIR, "summary-bar.png"),
    });
    await page.getByTestId("stage-strip").screenshot({
      path: path.join(S19_DIR, "stage-strip.png"),
    });
    await page.getByTestId("sync-banner").screenshot({
      path: path.join(S19_DIR, "sync-banner.png"),
    });

    // Expanded client — click the first client row → /clients/:id.
    // Slice 1 does not ship row-expand-in-place; row-click navigates
    // to the S13a client workspace. Capture that as the "expanded"
    // panel until slice 2's inline expand lands.
    const firstClient = page
      .getByTestId(/^client-row-/)
      .first();
    await firstClient.waitFor({ state: "visible" });
    await firstClient.click();
    await page.waitForURL(/\/clients\/[0-9a-f-]{36}/, { timeout: 30_000 });
    // Wait for the "Fetching the client." skeleton to leave the DOM before
    // shooting; networkidle fires too early on the workspace.
    await expect(page.getByText("Fetching the client.")).toHaveCount(0, {
      timeout: 30_000,
    });
    await page.waitForLoadState("networkidle", { timeout: 30_000 });
    await page.screenshot({
      path: path.join(S19_DIR, "expanded-client.png"),
      fullPage: true,
    });

    // Opportunities view.
    await page.goto(`${BASE}/pipeline`);
    await page.getByRole("tab", { name: /^Opportunities/ }).click();
    await expect(page.getByTestId("opportunities-table")).toBeVisible();
    await page.screenshot({
      path: path.join(S19_DIR, "opportunities-view.png"),
      fullPage: true,
    });
  });
});
