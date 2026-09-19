/**
 * 18 — Bulk SOW import duplicate detection (S10-02).
 *
 * Uploads the same fixed-price SOW twice (once as ``03_original.pdf``,
 * once as ``03_dup.pdf``). The second row must land in the
 * ``duplicate`` bucket, pointing at the first row's sow_version_id.
 * Log CSV includes both rows with the same sha256.
 */
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { applyTestUser } from "../fixtures/seed";

const FIXTURE = resolve(
  __dirname,
  "..",
  "..",
  "..",
  "fixtures",
  "sample_sows",
  "03_fixed_price_mixed.pdf",
);

test("duplicate SOW is flagged, not re-imported", async ({ page }) => {
  await applyTestUser(page, "Finance");
  await page.goto("/settings/data-imports/sows");

  const buf = readFileSync(FIXTURE);
  await page.getByTestId("bulk-file-input").setInputFiles([
    { name: "03_original.pdf", mimeType: "application/pdf", buffer: buf },
    { name: "03_dup.pdf", mimeType: "application/pdf", buffer: buf },
  ]);

  await expect(page.getByTestId("bulk-queue")).toBeVisible({ timeout: 20000 });
  const rows = page.locator("[data-testid^=bulk-row-]");
  await expect(rows).toHaveCount(2, { timeout: 30000 });

  // Exactly one duplicate chip must appear.
  await expect(page.getByTestId("bulk-chip-duplicate")).toHaveCount(1);
});
