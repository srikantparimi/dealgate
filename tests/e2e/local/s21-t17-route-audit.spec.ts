import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:5211" });

test("T17.06/.08 released fixture route identity, counts and reader isolation", async ({ page, request }) => {
  test.setTimeout(240_000);
  const f = JSON.parse(readFileSync("/tmp/s21-t17-61d71c0b.json", "utf8"));
  const database = "s21_t17_61d71c0b4bf7436d957723c632fe1aba";
  const deal = "0a66db62-3619-4762-a96e-afe1473864a9";
  const project = "aa26879a-826c-445f-9792-4a995039b409";
  expect(f.database).toBe(database);
  expect(f.fixture.opportunity_id).toBe(deal);
  const client = f.fixture.client_id as string;
  expect(client).toMatch(/^[0-9a-f-]{36}$/);
  let actor = f.people.owner.email;
  const evidence: unknown[] = [];
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/**", route => {
    // Auth boundary only; never replace a feature response or permit business writes.
    expect(route.request().method()).toBe("GET");
    return route.continue({ headers: { ...route.request().headers(), "X-Test-User": actor } });
  });
  async function get(path: string) {
    const response = await request.get(`http://127.0.0.1:8211${path}`, { headers: { "X-Test-User": actor } });
    expect(response.status(), path).toBe(200);
    return response.json();
  }
  function counts() {
    const sql = `BEGIN READ ONLY; SELECT json_build_object(
      'database',current_database(),
      'deals',(SELECT count(*) FROM opportunity WHERE id='${deal}'),
      'open',(SELECT count(*) FROM opportunity WHERE id='${deal}' AND NOT is_closed_won AND NOT is_closed_lost),
      'sows',(SELECT count(*) FROM sow WHERE opportunity_id='${deal}'),
      'packages',(SELECT count(*) FROM approval_package WHERE opportunity_id='${deal}'),
      'projects',(SELECT count(*) FROM project WHERE opportunity_id='${deal}'),
      'project_id',(SELECT id FROM project WHERE opportunity_id='${deal}' LIMIT 1)); COMMIT;`;
    const output = execFileSync("docker", ["exec", "dealgate-s21-lead-db", "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-U", "s21", "-d", database, "-c", sql], { encoding: "utf8" });
    return JSON.parse(output.trim());
  }
  const before = counts();
  expect(before).toMatchObject({ database, deals: 1, sows: 1, packages: 1, projects: 1, project_id: project });
  const account = await get(`/clients/${client}`);
  const detail = await get(`/pipeline/opportunities/${deal}`);
  const workspaceDeal = await get(`/deals/${deal}`);
  const version = await get(`/sow/opportunity/${deal}/current`);
  // This source has no extracted title: workspaceTitle uses client + optional
  // engagement type. Assert the authored fixture name, not an invented field.
  const title = "S21 e2e b76499f4-64d0-4b29-938f-b8217e3010d0 T17 connected 61d71c0b";
  expect(account.name).toBe(title);
  expect(workspaceDeal.client_name).toBe(title);
  expect(workspaceDeal.engagement_type).toBeNull();
  expect(detail.name).toBe(title);
  expect(detail.opportunity_id).toBe(deal);
  expect(detail.client_id).toBe(client);
  expect(detail.sow_count).toBe(1);
  expect(version.id).toBe("d95a10b3-9811-418a-b6ef-958d148c00b7");
  expect(version.opportunity_id).toBe(deal);
  expect(version.file_hash).toBe("7104c0fe8432aac30032689e0e8d89d6fe752bff0001b730826f08083561c0fc");
  expect(version.file_s3_key).toContain("s21-t17-61d71c0b-sow.docx");
  const open = await get(`/pipeline/opportunities?client=${client}&page_size=100`);
  const all = await get(`/pipeline/opportunities?client=${client}&include_closed=true&page_size=100`);
  const summary = await get(`/pipeline/summary?client=${client}`);
  expect(open.total).toBe(before.open);
  expect(summary.open_count).toBe(before.open);
  expect(all.total).toBe(1);
  expect(all.items.map((row: { opportunity_id: string }) => row.opportunity_id)).toEqual([deal]);
  const clients = await get(`/pipeline/clients?client=${client}&include_closed=true&page_size=100`);
  expect(clients.items).toHaveLength(1);
  expect(clients.items[0]).toMatchObject({ client_id: client, matching_deal_count: 1, total_open_deal_count: before.open });
  const projects = await get("/projects");
  expect(projects.items.filter((row: { provenance: { opportunity_id: string } }) => row.provenance.opportunity_id === deal)
    .map((row: { project_id: string }) => row.project_id)).toEqual([project]);

  await page.goto("/pipeline");
  if (before.open === 1) await expect(page.getByTestId(`client-row-${client}`)).toContainText(account.name);
  await page.goto(`/clients/${client}`);
  await expect(page.getByTestId("client-heading")).toHaveText(account.name);
  await expect(page.getByTestId("rollup-open")).toHaveText(String(before.open));
  await expect(page.getByTestId(`client-deal-row-${deal}`)).toHaveCount(1);
  await page.getByTestId(`client-deal-row-${deal}`).click();
  await expect(page).toHaveURL(new RegExp(`/deals/${deal}$`));
  await expect(page.getByTestId("deal-heading")).toHaveText(detail.name);
  await expect(page.getByRole("region", { name: "Readiness", exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId("deal-heading")).toHaveText(detail.name);
  const tabs = { overview: "Overview", scope: "Scope", staffing: "Staffing & GM", approvals: "Approvals",
    documents: "Documents", signature: "Signature", handoff: "Handoff", activity: "Activity" };
  async function shell(tab: string, label: string) {
    await expect(page).toHaveURL(new RegExp(`/sows/${deal}/${tab}$`));
    await expect(page.getByRole("heading", { name: title, exact: true })).toHaveCount(1);
    await expect(page.getByTestId("sow-version")).toHaveText(`SOW v ${version.version_no}`);
    await expect(page.getByRole("tab", { name: label, exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("region", { name: "Readiness", exact: true })).toHaveCount(1);
    for (const name of Object.values(tabs)) await expect(page.getByRole("tab", { name, exact: true })).toHaveCount(1);
  }
  for (const [tab, label] of Object.entries(tabs)) {
    await page.goto(`/sows/${deal}/${tab}`);
    await shell(tab, label);
    await page.reload();
    await shell(tab, label);
    evidence.push({ route: `/sows/${deal}/${tab}`, source_version: version.id, reload: true });
  }
  await page.getByRole("tab", { name: "Staffing & GM", exact: true }).click();
  await shell("staffing", "Staffing & GM");
  await page.getByRole("tab", { name: "Signature", exact: true }).click();
  await shell("signature", "Signature");
  await page.goBack();
  await shell("staffing", "Staffing & GM");
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  const header = page.getByTestId("workspace-header");
  await expect(header).toHaveCSS("position", "sticky");
  const geometry = await header.evaluate(element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    const point = document.elementFromPoint(rect.left + rect.width / 2, rect.top + Math.min(20, rect.height / 2));
    return { top: rect.top, bottom: rect.bottom, background: style.backgroundColor,
      configuredTop: style.top, coveredByHeader: !!point && element.contains(point) };
  });
  expect(geometry.configuredTop).toBe("56px");
  expect(geometry.top).toBeGreaterThanOrEqual(55);
  expect(geometry.background).not.toMatch(/transparent|rgba\([^)]*,\s*0\)$/);
  expect(geometry.coveredByHeader).toBe(true);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t17-route-sticky-header.png", fullPage: false });
  evidence.push({ geometry });
  expect(counts()).toEqual(before);

  actor = f.people.normal.email;
  const normal = await get("/me");
  expect(normal.groups).toContain("SystemAdmin");
  expect(normal.groups).not.toContain("officeapp-e2e");
  for (const path of ["/clients?size=200", "/deals?size=200", "/pipeline/opportunities?include_closed=true&page_size=100", "/pipeline/clients?include_closed=true&page_size=100", "/projects"]) {
    const body = await get(path);
    expect(JSON.stringify(body), path).not.toContain(deal);
    expect(JSON.stringify(body), path).not.toContain(client);
    expect(JSON.stringify(body), path).not.toContain(project);
  }
  for (const path of [`/clients/${client}`, `/deals/${deal}`, `/pipeline/opportunities/${deal}`, `/sow/opportunity/${deal}/current`]) {
    const response = await request.get(`http://127.0.0.1:8211${path}`, { headers: { "X-Test-User": actor } });
    expect([403, 404], path).toContain(response.status());
    expect(await response.text()).not.toContain(account.name);
    evidence.push({ normal_direct_api: path, status: response.status() });
  }
  for (const path of ["/pipeline", `/clients/${client}`, `/deals/${deal}`, `/sows/${deal}/overview`]) {
    await page.goto(path);
    await expect(page.getByText(/Loading (client|deal|SOW)/)).toHaveCount(0);
    await expect(page.getByTestId("client-heading")).toHaveCount(0);
    await expect(page.getByTestId("deal-heading")).toHaveCount(0);
    await expect(page.getByTestId("sow-version")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Delete SOW", exact: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: title, exact: true })).toHaveCount(0);
  }
  expect(errors).toEqual([]);
  expect(counts()).toEqual(before);
  writeFileSync("../../docs/s21/evidence/baseline/t17-route-audit.json", JSON.stringify({
    revision: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(), database,
    boundary: "Read-only local identity adapter, actual API/DB/UI; not Cognito or staging", counts: before,
    source_version: version.id, evidence, errors,
  }, null, 2));
});
