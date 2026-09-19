/**
 * 06 — submit_package returns 409 when NDA missing; the UI surfaces the
 * message on the deal page.
 */
import { expect, test } from "@playwright/test";
import { apiFetch } from "../fixtures/api";
import {
  applyTestUser,
  confirmAllSowFields,
  seedAgreement,
  seedClientWithDeal,
  seedGmModel,
  seedSowVersion,
} from "../fixtures/seed";

test.describe.configure({ mode: "serial" });

test("submit_package with missing NDA returns 409, UI shows the block", async ({
  page,
}) => {
  const { client, opportunityId } = await seedClientWithDeal({});
  // Only seed MSA — NDA deliberately missing.
  await seedAgreement(client.legal_entity_id, "MSA", "executed");
  const sow = await seedSowVersion(opportunityId, "Sales");
  await confirmAllSowFields(sow.id, "Sales");
  await seedGmModel({ opportunityId, sowVersionId: sow.id, belowFloor: false });

  const res = await apiFetch(
    "Delivery",
    "POST",
    `/approvals/packages/${opportunityId}`,
    undefined,
    { allowNon2xx: true },
  );
  expect(res.status).toBe(409);
  expect(res.text.toLowerCase()).toContain("nda");

  await applyTestUser(page, "Delivery");
  await page.goto(`/deals/${opportunityId}`);
  // The Approval panel renders a coverage-missing hint. The exact copy
  // includes "NDA" so we match on that.
  await expect(page.getByText(/nda/i)).toBeVisible();
});
