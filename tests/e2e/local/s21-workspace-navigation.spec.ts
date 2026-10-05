import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("T02 workspace preserves SOW identity, shell and readiness through tabs, Back and reload", async ({ page, request }) => {
  test.setTimeout(120_000);
  const root = resolve(process.cwd(), "../..");
  const base = "http://127.0.0.1:8210";
  const headers = { "X-Test-User": `s21-t02-${randomUUID()}@example.test` };
  await page.route("**/api/**", route => route.continue({
    headers: { ...route.request().headers(), ...headers },
  }));
  const issued = await request.post(`${base}/dev/test-fixtures`, { headers,
    data: { label: "T02 isolated navigation", reviewer_ids: [] } });
  expect(issued.status()).toBe(201);
  const fixture = await issued.json();
  // Declared synthetic SOW state; this test does not claim extraction quality.
  const output = execFileSync(`${root}/api/.venv/bin/python`, ["scripts/s21_conflict_review_journey.py"], {
    cwd: root, encoding: "utf8", timeout: 30_000, env: { ...process.env,
      PYTHONPATH: `${root}/api:${root}`, POSTGRES_URL: "postgresql+asyncpg://s21@127.0.0.1:55421/s21_journey",
      DEALGATE_ENV: "local", DEALGATE_TENANT_ID: "s21-lead", S21_REVIEW_DEAL: fixture.opportunity_id },
  });
  const source = JSON.parse(output.trim().split("\n").at(-1)!);
  const beforeResponse = await request.get(`${base}/sow/versions/${source.version_id}`, { headers });
  expect(beforeResponse.status()).toBe(200);
  const before = await beforeResponse.json();
  const shell = async (tab: string, label: string) => {
    await expect(page).toHaveURL(new RegExp(`/sows/${source.deal_id}/${tab}$`));
    await expect(page.getByRole("heading", { name: "Source conflict review", exact: true })).toBeVisible();
    await expect(page.getByTestId("sow-version")).toHaveText(`SOW v ${before.version_no}`);
    await expect(page.getByRole("tab", { name: label, exact: true })).toHaveAttribute("aria-selected", "true");
    for (const name of ["Overview", "Staffing & GM", "Approvals"]) {
      await expect(page.getByRole("tab", { name, exact: true })).toBeVisible();
    }
    const readiness = page.getByRole("region", { name: "Readiness", exact: true });
    await expect(readiness).toHaveCount(1);
    await expect(readiness).toBeVisible();
    const current = await request.get(`${base}/sow/opportunity/${source.deal_id}/current`, { headers });
    expect(current.status()).toBe(200);
    expect((await current.json()).id).toBe(source.version_id);
  };
  await page.goto(`/sows/${source.deal_id}/overview`);
  await shell("overview", "Overview");
  await page.getByRole("tab", { name: "Staffing & GM", exact: true }).click();
  await shell("staffing", "Staffing & GM");
  await page.getByRole("tab", { name: "Approvals", exact: true }).click();
  await shell("approvals", "Approvals");
  await page.goBack();
  await shell("staffing", "Staffing & GM");
  await page.goBack();
  await shell("overview", "Overview");
  await page.goto(`/sows/${source.deal_id}/approvals`);
  await shell("approvals", "Approvals");
  await page.reload();
  await shell("approvals", "Approvals");
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t02-workspace.png", fullPage: true });
  const after = await request.get(`${base}/sow/versions/${source.version_id}`, { headers });
  expect(after.status()).toBe(200);
  expect(await after.json()).toEqual(before);
});
