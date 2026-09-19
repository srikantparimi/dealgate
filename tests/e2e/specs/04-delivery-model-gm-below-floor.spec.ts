/**
 * 04 — Delivery builds a model with US GM = 27.78% (below the 35 %
 * floor) → submit for approval → package routed to CEO exception
 * instead of Ready-to-Sign.
 */
import { expect, test } from "@playwright/test";
import {
  applyTestUser,
  confirmAllSowFields,
  seedAgreement,
  seedClientWithDeal,
  seedGmModel,
  seedSowVersion,
  submitApprovalPackage,
} from "../fixtures/seed";

test.describe.configure({ mode: "serial" });

test("below-floor GM routes package to CEO exception, blocks Ready-to-Sign", async ({
  page,
}) => {
  const { client, opportunityId } = await seedClientWithDeal({});
  await seedAgreement(client.legal_entity_id, "NDA", "executed");
  await seedAgreement(client.legal_entity_id, "MSA", "executed");
  const sow = await seedSowVersion(opportunityId, "Sales");
  await confirmAllSowFields(sow.id, "Sales");
  await seedGmModel({ opportunityId, sowVersionId: sow.id, belowFloor: true });

  const pkg = await submitApprovalPackage(opportunityId, "Delivery");
  expect(pkg.status).toMatch(/pending_ceo_exception|pending_delivery_hr/);

  await applyTestUser(page, "Delivery");
  await page.goto(`/deals/${opportunityId}`);

  // The DealDetail page's approval panel shows the CEO exception status.
  await expect(page.getByText(/ceo exception|below floor/i)).toBeVisible();

  // Ready-to-Sign must NOT be present.
  await expect(page.getByText(/ready to sign/i)).toHaveCount(0);
});
