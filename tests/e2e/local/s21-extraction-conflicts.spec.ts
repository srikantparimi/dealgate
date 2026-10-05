import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("source conflict review preserves a newer human correction and clears only explicit review", async ({ page, request }) => {
  test.setTimeout(120_000);
  const base = "http://127.0.0.1:8210";
  const headers = { "X-Test-User": "s21-browser@example.test" };
  const root = resolve(process.cwd(), "../..");
  const issued = await request.post(`${base}/dev/test-fixtures`, { headers,
    data: { label: "Extraction conflict review", reviewer_ids: [], hours: 4 } });
  expect(issued.status()).toBe(201);
  const fixture = await issued.json();
  const output = execFileSync(`${root}/api/.venv/bin/python`, ["scripts/s21_conflict_review_journey.py"], {
    cwd: root, encoding: "utf8", timeout: 30_000, env: { ...process.env, PYTHONPATH: `${root}/api:${root}`,
      POSTGRES_URL: "postgresql+asyncpg://s21@127.0.0.1:55421/s21_journey", DEALGATE_ENV: "local",
      DEALGATE_TENANT_ID: "s21-lead", S21_REVIEW_DEAL: fixture.opportunity_id },
  });
  const source = JSON.parse(output.trim().split("\n").at(-1)!);
  const conflictPath = `${base}/sow/versions/${source.version_id}/extraction-conflicts`;
  await page.goto(`/sows/new?opportunityId=${source.deal_id}`);
  const panel = page.getByRole("region", { name: "Extraction conflicts", exact: true });
  await expect(panel.getByText("25000.00", { exact: true })).toBeVisible();
  await expect(panel.getByText("90000.00", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Complete scope", exact: true })).toBeDisabled();
  await expect(page.getByText("Extraction needs review", { exact: true })).toBeVisible();
  const blocked = await request.post(`${base}/sow/${source.deal_id}/confirmation/submit`, { headers });
  expect(blocked.status()).toBe(422);
  expect(await blocked.text()).toContain("extraction_conflict:price");
  const change = await request.patch(`${base}/sow/versions/${source.version_id}/fields/price`, {
    headers, data: { value: "50000.00" },
  });
  expect(change.status()).toBe(200);
  await panel.getByRole("radio", { name: "Accept new extraction", exact: true }).check();
  await panel.getByLabel("Review reason", { exact: true }).fill("Review before another editor corrected the amount");
  await panel.getByRole("button", { name: "Save review", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("Extraction review changed");
  await expect(panel.getByLabel("Review reason")).toHaveValue("Review before another editor corrected the amount");
  await panel.getByRole("button", { name: "Reload conflicts", exact: true }).click();
  await expect(panel.getByText("50000.00", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 1000 });
  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/extraction-review-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "Open navigation", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/extraction-review-mobile.png" });
  await panel.getByRole("radio", { name: "Keep confirmed value", exact: true }).check();
  await panel.getByLabel("Review reason", { exact: true }).fill("Keep the newer source-reviewed human correction");
  await panel.getByRole("button", { name: "Save review", exact: true }).click();
  await expect(panel).not.toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "Extraction conflicts", exact: true })).not.toBeVisible();
  const state = await request.get(`${base}/sow/versions/${source.version_id}`, { headers });
  expect(state.status()).toBe(200);
  const version = await state.json();
  expect(version.extracted_fields.price.value).toBe("50000.00");
  expect(version.extracted_fields.price.provenance).toBe("manual");
  expect(version.extract_status).toBe("complete");
  const conflicts = await request.get(conflictPath, { headers });
  expect(conflicts.status()).toBe(200);
  expect(await conflicts.json()).toEqual({ items: [] });
});

test("missing currency stays unresolved until the source reviewer supplies CAD", async ({ page, request }) => {
  test.setTimeout(90_000);
  const base = "http://127.0.0.1:8210";
  const headers = { "X-Test-User": "s21-browser@example.test" };
  const root = resolve(process.cwd(), "../..");
  const issued = await request.post(`${base}/dev/test-fixtures`, { headers,
    data: { label: "Unresolved source currency", reviewer_ids: [], hours: 4 } });
  expect(issued.status()).toBe(201);
  const fixture = await issued.json();
  const output = execFileSync(`${root}/api/.venv/bin/python`, ["scripts/s21_conflict_review_journey.py"], {
    cwd: root, encoding: "utf8", timeout: 30_000, env: { ...process.env, PYTHONPATH: `${root}/api:${root}`,
      POSTGRES_URL: "postgresql+asyncpg://s21@127.0.0.1:55421/s21_journey", DEALGATE_ENV: "local",
      DEALGATE_TENANT_ID: "s21-lead", S21_REVIEW_DEAL: fixture.opportunity_id, S21_REVIEW_MISSING_CURRENCY: "1" },
  });
  const source = JSON.parse(output.trim().split("\n").at(-1)!);
  await page.goto(`/sows/new?opportunityId=${source.deal_id}`);
  await expect(page.getByTestId("field-missing-currency")).toBeVisible();
  await expect(page.getByRole("button", { name: "Complete scope", exact: true })).toBeDisabled();
  const before = await request.get(`${base}/sow/versions/${source.version_id}`, { headers });
  expect(before.status()).toBe(200);
  expect((await before.json()).extracted_fields.currency.value).toBeNull();
  const blocked = await request.post(`${base}/sow/${source.deal_id}/confirmation/submit`, { headers });
  expect(blocked.status()).toBe(422);
  expect(await blocked.text()).toContain("currency");
  const currency = page.getByTestId("field-row-currency");
  await currency.getByRole("button", { name: "Change Currency", exact: true }).click();
  await currency.getByRole("textbox", { name: "Edit Currency", exact: true }).fill("CAD");
  await currency.getByRole("button", { name: "Save Currency", exact: true }).click();
  await expect(currency.getByText("CAD", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Complete scope", exact: true })).toBeEnabled();
  await page.reload();
  await expect(page.getByTestId("field-row-currency").getByText("CAD", { exact: true })).toBeVisible();
  const confirmed = await request.post(`${base}/sow/${source.deal_id}/confirmation/submit`, { headers });
  expect(confirmed.status()).toBe(200);
  const after = await request.get(`${base}/sow/versions/${source.version_id}`, { headers });
  expect(after.status()).toBe(200);
  const version = await after.json();
  expect(version.extracted_fields.currency.value).toBe("CAD");
  expect(version.extracted_fields.currency.status).toBe("confirmed");
  expect(version.confirmed_at).toBeTruthy();
});
