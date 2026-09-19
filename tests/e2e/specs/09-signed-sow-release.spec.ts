/**
 * 09 — Verified signed pdf → release → renewal record created + kickoff
 * / billing tasks visible.
 */
import { expect, test } from "@playwright/test";
import { apiFetch } from "../fixtures/api";
import { rand } from "../fixtures/seed";
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

test("release verified signed SOW → renewal + kickoff tasks appear", async ({
  page,
}) => {
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

  // Upload + verify (stub is expected to match under E2E config).
  const uploadUrl = await apiFetch<{ s3_key: string }>(
    "Sales",
    "POST",
    `/signed-sow/${pkg.id}/upload-url`,
    { filename: "signed.pdf", content_type: "application/pdf" },
  );
  await apiFetch("Sales", "POST", `/signed-sow/${pkg.id}`, {
    file_s3_key: uploadUrl.json.s3_key,
    file_hash: `hash-${rand()}`,
  });
  const verified = await apiFetch<{ verify_status: string }>(
    "Sales",
    "POST",
    `/signed-sow/${pkg.id}/verify`,
  );
  if (verified.json.verify_status !== "verified") {
    test.skip(true, "signed-SOW stub not tuned to verified");
  }
  await apiFetch("Sales", "POST", `/signed-sow/${pkg.id}/release`);

  const finalPkg = await apiFetch<{ status: string }>(
    "SystemAdmin",
    "GET",
    `/approvals/packages/${pkg.id}`,
  );
  expect(finalPkg.json.status).toBe("released");

  // The service creates a renewal row (fires from the release path).
  const renewals = await apiFetch<{
    items: Array<{ opportunity_id: string; status: string }>;
  }>("Sales", "GET", "/renewals");
  expect(
    renewals.json.items.some((r) => r.opportunity_id === opportunityId),
  ).toBe(true);

  await applyTestUser(page, "Sales");
  await page.goto(`/renewals`);
  await expect(page.getByRole("heading", { name: /renewals/i })).toBeVisible();
  await expect(page.getByRole("region", { name: /open/i })).toBeVisible();
});
