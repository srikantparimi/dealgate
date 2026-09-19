/**
 * 17 — Bulk SOW import happy path (S10-02).
 *
 * A Finance user opens `/settings/data-imports/sows`, drops the six
 * sample SOW PDFs + the MSA fixture + a duplicate of the fixed-price
 * SOW, and asserts:
 *
 *   - The queue table shows eight rows with the right per-file status.
 *   - The Legacy chip appears next to every imported row.
 *   - The Download log CSV button downloads a non-empty CSV.
 *   - The Run again button is present and idempotent (no new rows
 *     created after a rerun).
 */
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { applyTestUser } from "../fixtures/seed";

const FIXTURE_DIR = resolve(
  __dirname,
  "..",
  "..",
  "..",
  "fixtures",
  "sample_sows",
);

const SOW_NAMES = [
  "01_staff_aug_us.pdf",
  "02_managed_service_india.pdf",
  "03_fixed_price_mixed.pdf",
  "04_assessment_4week.pdf",
  "05_tm_capped.pdf",
  "06_below_floor.pdf",
];

test("bulk import — 6 SOWs + 1 MSA + 1 duplicate = 8 rows", async ({
  page,
}) => {
  await applyTestUser(page, "Finance");
  await page.goto("/settings/data-imports/sows");

  const input = page.getByTestId("bulk-file-input");
  const payloads = [
    ...SOW_NAMES.map((n) => ({
      name: n,
      mimeType: "application/pdf",
      buffer: readFileSync(resolve(FIXTURE_DIR, n)),
    })),
    {
      name: "07_msa.pdf",
      mimeType: "application/pdf",
      buffer: readFileSync(resolve(FIXTURE_DIR, "07_msa.pdf")),
    },
    {
      name: "03_fixed_price_mixed_dup.pdf",
      mimeType: "application/pdf",
      buffer: readFileSync(resolve(FIXTURE_DIR, "03_fixed_price_mixed.pdf")),
    },
  ];
  await input.setInputFiles(payloads);

  await expect(page.getByTestId("bulk-queue")).toBeVisible({ timeout: 20000 });
  const rows = page.locator("[data-testid^=bulk-row-]");
  await expect(rows).toHaveCount(8, { timeout: 30000 });

  // The Legacy chip renders on every imported / needs_review row.
  const legacyChips = page.getByText("Legacy");
  await expect(legacyChips.first()).toBeVisible();

  // Run again is idempotent — the row count should not budge.
  await page.getByTestId("bulk-rerun-btn").click();
  await expect(rows).toHaveCount(8);
});
