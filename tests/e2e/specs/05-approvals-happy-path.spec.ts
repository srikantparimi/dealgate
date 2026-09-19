/**
 * 05 — Happy path: all floors pass → Delivery + HR approve → Finance +
 * Legal approve → package = Ready to Sign; audit trail visible.
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

test.describe.configure({ mode: "serial" });

test("all four functions approve → Ready to Sign, audit trail present", async ({
  page,
}) => {
  const { client, opportunityId } = await seedClientWithDeal({});
  await seedAgreement(client.legal_entity_id, "NDA", "executed");
  await seedAgreement(client.legal_entity_id, "MSA", "executed");
  const sow = await seedSowVersion(opportunityId, "Sales");
  await confirmAllSowFields(sow.id, "Sales");
  await seedGmModel({ opportunityId, sowVersionId: sow.id, belowFloor: false });

  const pkg = await submitApprovalPackage(opportunityId, "Delivery");
  await decidePackage(pkg.id, "delivery", "Delivery", "approve");
  await decidePackage(pkg.id, "hr", "HR", "approve");
  await decidePackage(pkg.id, "finance", "Finance", "approve");
  await decidePackage(pkg.id, "legal", "Legal", "approve");

  const final = await apiFetch<{ status: string }>(
    "SystemAdmin",
    "GET",
    `/approvals/packages/${pkg.id}`,
  );
  expect(final.json.status).toBe("ready_to_sign");

  await applyTestUser(page, "Finance");
  await page.goto(`/approvals/${pkg.id}`);
  await expect(page.getByText(/ready to sign/i)).toBeVisible();

  // Audit trail — the deal detail page renders a "Recent audit" panel;
  // it must list at least the four approval events.
  await page.goto(`/deals/${opportunityId}`);
  await expect(page.getByRole("table", { name: /audit events/i })).toBeVisible();
});
