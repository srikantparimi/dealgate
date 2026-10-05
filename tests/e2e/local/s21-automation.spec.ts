import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("configured source events refresh seven-person sourcing through a separate worker", async ({ page, request }) => {
  test.setTimeout(180_000);
  const base = "http://127.0.0.1:8210";
  const headers = { "X-Test-User": "s21-browser@example.test" };
  const root = resolve(process.cwd(), "../..");
  const env = { ...process.env, PYTHONPATH: `${root}/api:${root}`,
    POSTGRES_URL: "postgresql+asyncpg://s21@127.0.0.1:55421/s21_journey",
    DEALGATE_ENV: "local", DEALGATE_TENANT_ID: "s21-lead",
    DEALGATE_REPORTING_TIMEZONE: "America/Los_Angeles", DEALGATE_REPORTING_CURRENCY: "USD" };
  async function rule() {
    const response = await request.get(`${base}/people/sourcing/automation`, { headers });
    expect(response.status()).toBe(200);
    return response.json();
  }
  async function disable() {
    const current = await rule();
    if (current.enabled) {
      const response = await request.post(`${base}/people/sourcing/automation`, { headers, data: {
        expected_version_id: current.id, enabled: false, request_key: crypto.randomUUID(),
        reason: "Stop isolated browser fixture automation after proof", } });
      expect(response.status()).toBe(201);
    }
  }
  function drainWorker() {
    for (let batch = 0; batch < 10; batch++) {
      const output = execFileSync(`${root}/api/.venv/bin/python`, ["-m", "worker.sourcing_automation"],
        { cwd: root, env, encoding: "utf8", timeout: 60_000 });
      const result = JSON.parse(output.trim().split("\n").at(-1)!);
      expect(result.worker).toBe("sourcing_automation");
      if (result.handled === 0) return;
    }
    throw new Error("Automation queue did not drain within ten bounded batches");
  }
  await disable();
  const issued = await request.post(`${base}/dev/test-fixtures`, { headers,
    data: { label: "Automation browser", reviewer_ids: [], hours: 4 } });
  expect(issued.status()).toBe(201);
  const fixture = await issued.json();
  const output = execFileSync(`${root}/api/.venv/bin/python`, ["scripts/s21_automation_journey.py"], {
    cwd: root, encoding: "utf8", timeout: 30_000, env: { ...env, S21_AUTOMATION_DEAL: fixture.opportunity_id },
  });
  const source = JSON.parse(output.trim().split("\n").at(-1)!);
  const rulesResponse = await request.get(`${base}/people/sourcing/rules`, { headers });
  expect(rulesResponse.status()).toBe(200);
  const sourcingRules = await rulesResponse.json();
  const updatedRules = await request.post(`${base}/people/sourcing/rules`, { headers, data: {
    expected_version_id: sourcingRules.id, request_key: crypto.randomUUID(), reason: "Reviewed synthetic sourcing deadlines",
    rules: [{ skill: "python", location: "US", lead_days: 45 }, { skill: "python", location: "India", lead_days: 30 }],
  } });
  expect(updatedRules.status()).toBe(201);
  try {
    await page.goto("/people/sourcing");
    await page.getByRole("button", { name: "Automation", exact: true }).click();
    const panel = page.getByRole("region", { name: "Sourcing automation", exact: true });
    const enabled = panel.getByRole("checkbox", { name: "Automatic sourcing refresh" });
    await expect(enabled).toBeEnabled();
    await expect(enabled).not.toBeChecked();
    await enabled.check();
    await panel.getByLabel("Automation change reason").fill("Enable reviewed synthetic source refresh");
    await panel.getByRole("button", { name: "Save automation", exact: true }).click();
    await expect(panel.getByText(/Automation revision \d+ saved/)).toBeVisible();
    drainWorker();
    await page.getByRole("button", { name: "Reload latest", exact: true }).click();
    await page.getByLabel("Published source", { exact: true }).selectOption(source.plan_id);
    await expect(page.getByText("Win probability: 70.0%", { exact: true })).toBeVisible();
    const revised = await request.post(`${base}/forecast/plans/${source.plan_id}/assumptions`, { headers, data: {
      expected_version_id: source.version_id, probability: "0.40", probability_source: "Reviewed synthetic assessment",
      assumptions: ["Same seven-person scope"], lifecycle: "tentative", change_reason: "Probability change event proof",
    } });
    expect(revised.status()).toBe(201);
    drainWorker();
    await page.getByRole("button", { name: "Reload latest", exact: true }).click();
    await expect(page.getByText("Win probability: 40.0%", { exact: true })).toBeVisible();
    const historyResponse = await request.get(`${base}/people/sourcing/drafts?publication_id=${source.publication_id}`, { headers });
    expect(historyResponse.status()).toBe(200);
    const history = await historyResponse.json();
    expect(Number(history.items[0].snapshot.probability)).toBe(0.4);
    const before = history.items.find((item: { snapshot: { probability: string } }) => Number(item.snapshot.probability) === 0.7);
    expect(before).toBeTruthy();
    for (const revision of [history.items[0], before]) {
      const rows = revision.snapshot.rows.filter((row: { start: string }) => row.start === "2026-11-01");
      expect(rows.reduce((total: number, row: { quantity: number }) => total + row.quantity, 0)).toBe(7);
      expect(Object.fromEntries(rows.map((row: { location: string; sourcing_by: string }) => [row.location, row.sourcing_by])))
        .toEqual({ US: "2026-09-17", India: "2026-10-02" });
    }
    await panel.getByRole("button", { name: "Reload automation", exact: true }).click();
    await expect(panel.getByText(/Last success:/)).toBeVisible();
    await page.setViewportSize({ width: 1280, height: 1000 });
    await enabled.scrollIntoViewIfNeeded();
    await page.screenshot({ path: "../../docs/s21/evidence/baseline/automation-desktop.png" });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("button", { name: "Open navigation", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: "../../docs/s21/evidence/baseline/automation-mobile.png" });
    await enabled.uncheck();
    await panel.getByLabel("Automation change reason").fill("Disable after connected source event proof");
    await panel.getByRole("button", { name: "Save automation", exact: true }).click();
    await expect(enabled).not.toBeChecked();
    await expect.poll(async () => (await rule()).enabled).toBe(false);
  } finally {
    await disable();
  }
});
