/**
 * 02 — Coverage: Legal adds NDA + MSA → coverage state flips to
 * "Complete".
 */
import { expect, test } from "@playwright/test";
import { apiFetch } from "../fixtures/api";
import { applyTestUser, seedAgreement, seedClientWithDeal } from "../fixtures/seed";

test.describe.configure({ mode: "serial" });

test("coverage flips from 'NDA + MSA missing' to 'Complete'", async ({ page }) => {
  const { client, opportunityId } = await seedClientWithDeal({});

  // Baseline: no agreements yet → coverage_state != "Complete".
  const before = await apiFetch<{ coverage_state: string }>(
    "SystemAdmin",
    "GET",
    `/deals/${opportunityId}`,
  );
  expect(before.json.coverage_state).not.toBe("Complete");

  // Legal seeds NDA + MSA against the primary legal entity.
  await seedAgreement(client.legal_entity_id, "NDA", "executed");
  await seedAgreement(client.legal_entity_id, "MSA", "executed");

  await applyTestUser(page, "Legal");
  await page.goto(`/clients/${client.id}`);

  // The Agreements panel lists both agreements, and the deal page's
  // Coverage chip flips to "Complete".
  await expect(page.getByRole("heading", { name: /agreements/i })).toBeVisible();
  await expect(page.getByText("NDA", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("MSA", { exact: false }).first()).toBeVisible();

  await page.goto(`/deals/${opportunityId}`);
  await expect(page.getByText("Complete", { exact: false })).toBeVisible();
});
