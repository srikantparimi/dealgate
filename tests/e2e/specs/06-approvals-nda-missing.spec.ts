/**
 * 06 — missing NDA does not block functional review (S14b).
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

test("submit_package with missing NDA succeeds; workspace names the signature gate", async ({
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
  expect(res.status).toBe(201);

  await applyTestUser(page, "Delivery");
  await page.goto(`/sows/${opportunityId}/approvals`);
  await expect(page.getByText("NDA missing - blocks signature, not review.")).toBeVisible();
});
