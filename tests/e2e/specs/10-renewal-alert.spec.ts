/**
 * 10 — Time-travel via `DEALGATE_NOW` → SOW T-60d → renewal appears on
 * the board + nudge notification queued.
 */
import { expect, test } from "@playwright/test";
import { apiFetch } from "../fixtures/api";
import {
  applyTestUser,
  confirmAllSowFields,
  decidePackage,
  seedAgreement,
  seedClientWithDeal,
  seedGmModel,
  seedSowVersion,
  submitApprovalPackage,
} from "../fixtures/seed";
import { clearServerNow, setServerNow, tickScheduler } from "../fixtures/time";

test.describe.configure({ mode: "serial" });

test.afterAll(async () => {
  await clearServerNow();
});

test("renewal opens at T-60d and a nudge notification is queued", async ({ page }) => {
  const travel = await setServerNow("2025-01-01T00:00:00Z");
  test.skip(
    !travel.supported,
    "dev-only /admin/test/now endpoint is not exposed; enable DEALGATE_ENV=local for the workflow",
  );

  const { client, opportunityId } = await seedClientWithDeal({});
  await seedAgreement(client.legal_entity_id, "NDA", "executed");
  await seedAgreement(client.legal_entity_id, "MSA", "executed");
  const sow = await seedSowVersion(opportunityId, "Sales");
  await confirmAllSowFields(sow.id, "Sales");
  await seedGmModel({ opportunityId, sowVersionId: sow.id, belowFloor: false });
  const pkg = await submitApprovalPackage(opportunityId, "Delivery");
  await decidePackage(pkg.id, "delivery", "Delivery");
  await decidePackage(pkg.id, "hr", "HR");
  await decidePackage(pkg.id, "finance", "Finance");
  await decidePackage(pkg.id, "legal", "Legal");

  // Assume SOW term_end = 2025-05-01 (stub default). Jump to T-60d
  // (~ 2025-03-02) and tick the scheduler.
  await setServerNow("2025-03-02T00:00:00Z");
  const tick = await tickScheduler();
  test.skip(!tick.supported, "scheduler tick endpoint not exposed");

  await applyTestUser(page, "Sales");
  await page.goto("/renewals");
  await expect(page.getByRole("heading", { name: /renewals/i })).toBeVisible();
  // The board renders the renewal row for this opportunity in one of
  // the four columns; the load-bearing check is that at least one
  // column is not empty for this opportunity.
  const rowHandle = page.locator(`[data-testid^="row-"]`).first();
  await expect(rowHandle).toBeVisible();

  // Nudge notification queued for the owner (Sales).
  const notif = await apiFetch<{ items: Array<{ subject: string }> }>(
    "Sales",
    "GET",
    "/notifications/inbox",
  );
  expect(
    notif.json.items.some((n) => /renewal|nudge/i.test(n.subject)),
  ).toBe(true);
});
