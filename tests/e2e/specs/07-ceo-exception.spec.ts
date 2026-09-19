/**
 * 07 — CEO opens brief, owner writes rationale, CEO approves with
 * conditions + valid_until → package = Ready to Sign.
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
  submitApprovalPackage,
} from "../fixtures/seed";

test.describe.configure({ mode: "serial" });

test("owner rationale + CEO approve-with-conditions → Ready to Sign", async ({
  page,
}) => {
  const { client, opportunityId } = await seedClientWithDeal({});
  await seedAgreement(client.legal_entity_id, "NDA", "executed");
  await seedAgreement(client.legal_entity_id, "MSA", "executed");
  const sow = await seedSowVersion(opportunityId, "Sales");
  await confirmAllSowFields(sow.id, "Sales");
  await seedGmModel({ opportunityId, sowVersionId: sow.id, belowFloor: true });

  const pkg = await submitApprovalPackage(opportunityId, "Delivery");

  // The API creates a ceo_exception row when the package routes to
  // CEO. Fetch its id via the pending inbox.
  const inbox = await apiFetch<{ items: Array<{ id: string; package_id: string }> }>(
    "CEO",
    "GET",
    "/ceo-exceptions",
    undefined,
    { query: { status: "pending" } },
  );
  const exc = inbox.json.items.find((i) => i.package_id === pkg.id);
  expect(exc, "ceo exception row exists").toBeTruthy();
  const excId = exc!.id;

  // Owner writes the rationale.
  await apiFetch("Sales", "PATCH", `/ceo-exceptions/${excId}/rationale`, {
    rationale_text: "Strategic client, one-time discount to seed roadmap work.",
  });

  await applyTestUser(page, "CEO");
  await page.goto(`/ceo-exceptions/${excId}`);
  await expect(page.getByRole("heading", { name: /client/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /decision/i })).toBeVisible();

  // Post the CEO decision via API (the UI form is out of scope for this
  // assertion — we prove the state transition + Ready-to-Sign land).
  await apiFetch("CEO", "POST", `/ceo-exceptions/${excId}/decisions`, {
    decision: "approve",
    conditions_text: "Renegotiate at renewal to floor.",
    valid_until: "2026-12-31",
  });

  const final = await apiFetch<{ status: string }>(
    "SystemAdmin",
    "GET",
    `/approvals/packages/${pkg.id}`,
  );
  expect(final.json.status).toBe("ready_to_sign");
});
