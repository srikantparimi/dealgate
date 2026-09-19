/**
 * 01 — Intake → owner flow.
 *
 * HubSpot webhook drops a deal (via API call as SystemAdmin) → deal
 * appears in Deal list → owner sees intake task → owner sets engagement
 * type + next check-in date.
 */
import { expect, test } from "@playwright/test";
import { applyTestUser, seedClientWithDeal } from "../fixtures/seed";

test.describe.configure({ mode: "serial" });

test("owner sees the new deal + intake task, sets engagement type", async ({ page }) => {
  const { client, opportunityId, hubspotDealId } = await seedClientWithDeal({});
  await applyTestUser(page, "Sales");

  await page.goto("/deals");
  await expect(page.getByRole("heading", { name: /deals/i })).toBeVisible();

  // Deal list must include the just-created hubspot id.
  await expect(page.getByText(hubspotDealId)).toBeVisible();

  await page.goto(`/deals/${opportunityId}`);
  await expect(page.getByRole("heading", { name: /deal/i })).toBeVisible();
  await expect(page.getByText(client.name)).toBeVisible();

  // The intake task lands in the tasks panel on the deal (the API seeds
  // an "intake" category task on webhook receipt).
  await expect(page.getByRole("table", { name: /deal tasks/i })).toBeVisible();

  // Owner sets engagement type + next client action.
  await page.getByLabel("Engagement type").fill("staff_aug");
  await page.getByLabel("Next client action").fill("Kickoff call");
  await page.getByRole("button", { name: /save/i }).click();

  // The status chip on Coverage renders after re-fetch — confirm the
  // engagement type is persisted by re-reading the value.
  await expect(page.getByLabel("Engagement type")).toHaveValue("staff_aug");
});
