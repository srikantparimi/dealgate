import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("released project demand survives SOW deletion and keeps sourcing history", async ({ page, request }) => {
  test.setTimeout(120_000);
  const headers = { "X-Test-User": "s21-browser@example.test" };
  const base = "http://127.0.0.1:8210";
  const issued = await request.post(`${base}/dev/test-fixtures`, { headers,
    data: { label: "Retained demand browser", reviewer_ids: [], hours: 4 } });
  expect(issued.status()).toBe(201);
  const fixture = await issued.json();
  const root = resolve(process.cwd(), "../..");
  const output = execFileSync(resolve(root, "api/.venv/bin/python"), ["scripts/s21_retained_journey.py"], {
    cwd: root, encoding: "utf8", timeout: 30_000,
    env: { ...process.env, PYTHONPATH: resolve(root, "api"),
      POSTGRES_URL: "postgresql+asyncpg://s21@127.0.0.1:55421/s21_journey",
      DEALGATE_ENV: "local", DEALGATE_TENANT_ID: "s21-lead", S21_RETAINED_DEAL: fixture.opportunity_id },
  });
  const seeded = JSON.parse(output.trim().split("\n").at(-1)!);
  expect(seeded.fixture_kind).toBe("seeded_release_not_signature_proof");
  await page.goto("/people/demand");
  const source = page.getByRole("region", { name: seeded.title, exact: true });
  await source.getByRole("button", { name: "Publish demand", exact: true }).click();
  await source.getByLabel("Publication reason", { exact: true }).fill("Publish approved staffing to HR");
  await source.getByRole("button", { name: "Publish latest source", exact: true }).click();
  await expect(source).toContainText("Skills unknown");
  await source.getByRole("button", { name: "Revise demand", exact: true }).click();
  await source.getByLabel("Skills for Engineer", { exact: true }).fill("python");
  await source.getByLabel("Level for Engineer", { exact: true }).fill("senior");
  await source.getByLabel("Evidence for Engineer", { exact: true }).fill("Synthetic HR reviewed approved two-person team");
  await source.getByLabel("Publication reason", { exact: true }).fill("Confirm retained capability");
  await source.getByRole("button", { name: "Publish latest source", exact: true }).click();
  await expect(source).not.toContainText("Skills unknown");
  await expect(source).toContainText("committed");
  const previousRules = await request.get(`${base}/people/sourcing/rules`, { headers });
  expect(previousRules.status()).toBe(200);
  const configured = await request.post(`${base}/people/sourcing/rules`, { headers, data: {
    expected_version_id: (await previousRules.json()).id, request_key: crypto.randomUUID(),
    reason: "Synthetic retained journey lead time", rules: [{ skill: "python", location: "US", lead_days: 45 }],
  } });
  expect(configured.status()).toBe(201);
  await page.goto("/people/sourcing");
  await page.getByLabel("Published source", { exact: true }).selectOption(seeded.project_id);
  await page.getByLabel("Draft reason", { exact: true }).fill("Retained project sourcing before deletion");
  await page.getByRole("button", { name: "Prepare sourcing draft", exact: true }).click();
  await expect(page.getByText("Sourcing draft revision 1 prepared", { exact: true })).toBeVisible();
  const before = await request.get(`${base}/people/demand`, { headers });
  const publication = (await before.json()).items.find((item: { project_id: string }) => item.project_id === seeded.project_id);
  const stableKeys = publication.lines.map((line: { demand_key: string }) => line.demand_key);
  await page.goto(`/sows/${fixture.opportunity_id}/overview`);
  await page.getByRole("button", { name: "Delete SOW", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Delete this SOW?" });
  await expect(dialog).toContainText("Projects and financial actuals are retained");
  await dialog.getByRole("button", { name: "Delete SOW", exact: true }).click();
  await expect(page.getByRole("heading", { name: "SOW deletion", exact: true })).toBeVisible();
  await expect(page.getByText("File cleanup complete", { exact: true })).toBeVisible();
  await page.goto("/people/demand");
  await expect(source).toContainText("Synthetic HR reviewed approved two-person team");
  await expect(source.getByRole("row").filter({ hasText: "America/New_York" }).getByRole("cell").nth(2)).toHaveText("2");
  const after = await request.get(`${base}/people/demand`, { headers });
  const retained = (await after.json()).items.find((item: { project_id: string }) => item.project_id === seeded.project_id);
  expect(retained.lines.map((line: { demand_key: string }) => line.demand_key)).toEqual(stableKeys);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/retained-demand-desktop.png", fullPage: true });
  await page.goto("/people/sourcing");
  await page.getByLabel("Published source", { exact: true }).selectOption(seeded.project_id);
  await expect(page.getByRole("article")).toContainText("Retained project sourcing before deletion");
  await page.getByLabel("Draft reason", { exact: true }).fill("Retained project sourcing after deletion");
  await page.getByRole("button", { name: "Prepare sourcing draft", exact: true }).click();
  await expect(page.getByText("Sourcing draft revision 2 prepared", { exact: true })).toBeVisible();
  const history = await request.get(`${base}/people/sourcing/drafts?publication_id=${publication.publication_id}`, { headers });
  expect(history.status()).toBe(200);
  expect((await history.json()).items.map((item: { revision: number }) => item.revision)).toEqual([2, 1]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/retained-sourcing-mobile.png", fullPage: true });
});
