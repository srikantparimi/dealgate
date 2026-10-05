import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("T18 expanded coverage edits, clears and pages immutable history from Forecast", async ({ page, request }) => {
  test.setTimeout(240_000);
  page.setDefaultTimeout(15_000);
  if (!process.env.S21_VIEWS_COVERAGE_MANIFEST) throw new Error("Require owned account C manifest");
  const f = JSON.parse(readFileSync(process.env.S21_VIEWS_COVERAGE_MANIFEST, "utf8"));
  expect(f.database).toMatch(/^s21_cov_37eb[0-9a-f]{28}$/);
  expect(f.status).toBe("ready_for_publication");
  const api = resolve(process.cwd(), "../../api");
  const worker = execFileSync(resolve(api, ".venv/bin/python"), ["-m", "worker.forecast_plans"], {
    cwd: resolve(api, ".."), encoding: "utf8", timeout: 60_000,
    env: { ...process.env, PYTHONPATH: api, POSTGRES_URL: `postgresql+asyncpg://s21@127.0.0.1:55421/${f.database}`,
      DEALGATE_ENV: "local", DEALGATE_TENANT_ID: f.database },
  });
  expect(JSON.parse(worker.trim().split("\n").at(-1)!).worker).toBe("forecast_plans");
  const headers = { "X-Test-User": f.actor_email };
  const base = "http://127.0.0.1:8210";
  const historyIds: { version_id: string; revision: number }[] = [];
  const checkpoint = (stage: string) => writeFileSync("../../docs/s21/evidence/baseline/t18-coverage-controls-proof.json", JSON.stringify({
    database: f.database, run_id: f.run_id, account_id: f.account_id, stage, history: historyIds,
  }, null, 2));
  async function get(path: string) {
    const response = await request.get(`${base}${path}`, { headers });
    expect(response.status()).toBe(200);
    return response.json();
  }
  async function quantities() {
    const result = await get(`/people/demand/allocation?account_id=${f.account_id}`);
    expect(result.is_reservation).toBe(false);
    expect(result.intervals.length).toBeGreaterThan(0);
    return result.intervals.map((row: { start: string; demands: { quantity: number }[] }) => ({
      start: row.start, heads: row.demands.reduce((sum, demand) => sum + demand.quantity, 0),
    }));
  }
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const url = `/forecast?view=resources&account_id=${f.account_id}&as_of=2026-10-15T12:00:00Z&future_quarters=2`;
  await page.goto(url);
  const persistedPlans = await get(`/forecast/plans?account_id=${f.account_id}`);
  expect(persistedPlans.items.find((item: { id: string }) => item.id === f.plan_id).job.status).toBe("done");
  const existing = (await get("/people/demand")).items;
  for (const title of [f.plan_title, f.project_title]) {
    const source = page.getByRole("region", { name: title, exact: true });
    if (existing.find((item: { title: string }) => item.title === title).state !== "current") {
      await source.getByRole("button", { name: "Publish demand", exact: true }).click();
      await source.getByLabel("Publication reason", { exact: true }).fill("Publish declared coverage-control source");
      await source.getByRole("button", { name: "Publish latest source", exact: true }).click();
    }
    await expect(source).toContainText("2027-01-01 to 2027-03-31");
    await source.getByRole("button", { name: "Revise demand", exact: true }).click();
    for (const [role, skill] of [["Engineer", "python"], ["Analyst", "analysis"]]) {
      await source.getByLabel(`Skills for ${role}`, { exact: true }).fill(skill);
      await source.getByLabel(`Level for ${role}`, { exact: true }).fill("Senior");
      await source.getByLabel(`Evidence for ${role}`, { exact: true }).fill(`Synthetic confirmed ${role} capability`);
    }
    await source.getByLabel("Publication reason", { exact: true }).fill("Confirm skills and level before staffing replacement");
    await source.getByRole("button", { name: "Publish latest source", exact: true }).click();
    await expect(source).not.toContainText("Skills unknown");
  }
  const sources = (await get("/people/demand")).items;
  const plan = sources.find((item: { plan_id: string }) => item.plan_id === f.plan_id);
  const project = sources.find((item: { project_id: string }) => item.project_id === f.project_id);
  expect(plan.state).toBe("current");
  expect(project.state).toBe("current");
  expect(plan.lines.every((row: { missing: string[] }) => row.missing.length === 0)).toBe(true);
  expect(project.lines.every((row: { missing: string[] }) => row.missing.length === 0)).toBe(true);
  expect((await get(`/people/demand/coverage?plan_publication_id=${plan.publication_id}`)).items).toEqual([]);
  expect((await quantities()).every((row: { heads: number }) => row.heads === 8)).toBe(true);
  const source = page.getByRole("region", { name: f.plan_title, exact: true });
  await source.getByRole("button", { name: "Staffing coverage", exact: true }).click();
  const editor = source.getByRole("region", { name: "Staffing coverage", exact: true });
  await editor.getByLabel("Replacement project", { exact: true }).selectOption(project.publication_id);
  await editor.getByRole("button", { name: "Add mapping", exact: true }).click();
  const line = (record: typeof plan, role: string) => record.lines.find((item: { role: string }) => item.role === role).line_key;
  for (const role of ["Engineer", "Analyst"]) {
    await editor.getByLabel("Plan line 1", { exact: true }).selectOption(line(plan, role));
    await editor.getByLabel("Project line 1", { exact: true }).selectOption(line(project, role));
  }
  await editor.getByLabel("Plan first slot 1", { exact: true }).fill("2");
  await editor.getByLabel("Project first slot 1", { exact: true }).fill("2");
  await editor.getByLabel("Slot count 1", { exact: true }).fill("1");
  await editor.getByLabel("Start date 1", { exact: true }).fill("2027-01-15");
  await editor.getByLabel("End date 1", { exact: true }).fill("2027-02-15");
  await editor.getByRole("button", { name: "Add mapping", exact: true }).click();
  await editor.getByRole("button", { name: "Remove mapping 2", exact: true }).click();
  await expect(editor.getByLabel("Slot count 2", { exact: true })).not.toBeVisible();
  await editor.getByLabel("Coverage reason", { exact: true }).fill("One second Analyst slot for the explicit partial interval");
  await editor.getByRole("button", { name: "Save coverage", exact: true }).click();
  await expect(editor.getByText("Coverage revision 1 saved", { exact: true })).toBeVisible();
  let current = (await get(`/people/demand/coverage?plan_publication_id=${plan.publication_id}`)).items[0];
  const mapping = { plan_line_key: line(plan, "Analyst"), project_line_key: line(project, "Analyst"),
    plan_slots: [1], project_slots: [1], start_date: "2027-01-15", end_date: "2027-02-15" };
  expect(current.mappings).toEqual([mapping]);
  const covered = await quantities();
  expect(covered.find((row: { start: string }) => row.start === "2027-01-15")?.heads).toBe(7);
  expect(covered.find((row: { start: string }) => row.start === "2027-02-16")?.heads).toBe(8);
  historyIds.push({ version_id: current.version_id, revision: current.revision });
  checkpoint("mapped");
  await page.reload();
  await source.getByRole("button", { name: "Staffing coverage", exact: true }).click();
  await editor.getByLabel("Replacement project", { exact: true }).selectOption(project.publication_id);
  await expect(editor.getByLabel("Plan first slot 1", { exact: true })).toHaveValue("2");
  await expect(editor.getByLabel("Start date 1", { exact: true })).toHaveValue("2027-01-15");
  await editor.getByLabel("Coverage reason", { exact: true }).fill("Clear the partial interval after review");
  await editor.getByRole("button", { name: "Clear coverage", exact: true }).click();
  await expect(editor.getByText("Coverage revision 2 saved", { exact: true })).toBeVisible();
  current = (await get(`/people/demand/coverage?plan_publication_id=${plan.publication_id}`)).items[0];
  expect(current.mappings).toEqual([]);
  expect((await quantities()).every((row: { heads: number }) => row.heads === 8)).toBe(true);
  historyIds.push({ version_id: current.version_id, revision: current.revision });
  checkpoint("cleared");
  // Real versioned API writes produce the second history page; no mocked page responses.
  for (let revision = 3; revision <= 51; revision++) {
    const response = await request.post(`${base}/people/demand/coverage`, { headers, data: {
      plan_publication_id: plan.publication_id, project_publication_id: project.publication_id,
      expected_plan_version_id: plan.publication_version_id, expected_project_version_id: project.publication_version_id,
      expected_mapping_version_id: current.version_id, request_key: crypto.randomUUID(),
      reason: `Synthetic history revision ${revision}`, mappings: revision % 2 ? [mapping] : [],
    } });
    expect(response.status()).toBe(201);
    current = await response.json();
    expect(current.revision).toBe(revision);
    historyIds.push({ version_id: current.version_id, revision });
    checkpoint("history-building");
  }
  await editor.getByRole("button", { name: "Reload latest coverage", exact: true }).click();
  const selector = editor.getByLabel("Coverage history revision", { exact: true });
  await expect(selector.locator("option")).toHaveCount(50);
  await selector.selectOption(historyIds[48].version_id);
  await expect(editor.getByText("Synthetic history revision 49", { exact: true })).toBeVisible();
  await editor.getByRole("button", { name: "Next coverage page", exact: true }).click();
  await expect(selector.locator("option")).toHaveCount(1);
  await expect(editor).toContainText("History page 2");
  await expect(editor.getByRole("button", { name: "Next coverage page", exact: true })).toBeDisabled();
  await selector.selectOption(historyIds[0].version_id);
  await expect(editor.getByText("One second Analyst slot for the explicit partial interval", { exact: true })).toBeVisible();
  await editor.getByRole("button", { name: "Previous coverage page", exact: true }).click();
  await expect(selector.locator("option")).toHaveCount(50);
  await expect(editor.getByRole("button", { name: "Previous coverage page", exact: true })).toBeDisabled();
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t18-coverage-history.png", fullPage: true });
  await source.getByRole("button", { name: "Staffing coverage", exact: true }).click();
  await expect(editor).not.toBeVisible();
  checkpoint("passed");
});
