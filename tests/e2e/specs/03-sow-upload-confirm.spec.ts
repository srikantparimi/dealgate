/**
 * 03 — Owner uploads a SOW → confirm-fields screen renders → confirm
 * each field → submit → status moves to SOWDraft.confirmed.
 */
import { expect, test } from "@playwright/test";
import { apiFetch } from "../fixtures/api";
import {
  applyTestUser,
  seedClientWithDeal,
  seedSowVersion,
} from "../fixtures/seed";

test.describe.configure({ mode: "serial" });

test("owner confirms extracted SOW fields and submits", async ({ page }) => {
  const { opportunityId } = await seedClientWithDeal({});
  const sow = await seedSowVersion(opportunityId, "Sales");

  await applyTestUser(page, "Sales");
  await page.goto(`/deals/${opportunityId}`);

  // The SOW panel mounts the SOWConfirm view once a version exists —
  // the aria-labeled confirm buttons are the load-bearing assertion.
  await expect(page.getByRole("heading", { name: /^sow$/i })).toBeVisible();
  await expect(
    page.getByRole("button", { name: /^confirm (price|scope summary)/i }).first(),
  ).toBeVisible();

  // Drive the "submit for GM build" button once the extract is
  // confirmed. The seed helper leaves fields unconfirmed so we
  // patch each field via the API (mimicking multiple clicks) and
  // then click Submit in the UI.
  const v = await apiFetch<{ extracted_fields: Record<string, { value: unknown }> }>(
    "Sales",
    "GET",
    `/sow/versions/${sow.id}`,
  );
  for (const [name, field] of Object.entries(v.json.extracted_fields ?? {})) {
    await apiFetch("Sales", "PATCH", `/sow/versions/${sow.id}/fields/${name}`, {
      value: field.value,
    });
  }
  await page.reload();
  await page.getByRole("button", { name: /submit for gm build/i }).click();

  const after = await apiFetch<{ confirmed_at: string | null }>(
    "SystemAdmin",
    "GET",
    `/sow/versions/${sow.id}`,
  );
  expect(after.json.confirmed_at).not.toBeNull();
});
