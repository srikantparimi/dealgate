import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("T09 real filtered Pipeline population survives export, navigation and stale responses", async ({ page, request }, testInfo) => {
  test.setTimeout(120_000);
  expect(process.env.S21_FILTER_MANIFEST, "Explicit isolated fixture manifest required").toBeTruthy();
  const fixture = JSON.parse(readFileSync(process.env.S21_FILTER_MANIFEST!, "utf8"));
  expect(fixture.database).toMatch(/^s21_filter_[0-9a-f]{32}$/);
  const api = "http://127.0.0.1:8210";
  const headers = { "X-Test-User": fixture.actor_email };
  const me = await request.get(`${api}/me`, { headers });
  expect(me.ok()).toBe(true);
  expect((await me.json()).groups).toEqual(["SystemAdmin"]);
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const selected = fixture.expected.selected;
  const query = (filters: Record<string, any>) => {
    const params = new URLSearchParams({ sort: "client_name" });
    for (const [key, values] of Object.entries(filters)) for (const value of Array.isArray(values) ? values : [values]) params.append(key, value);
    return params;
  };
  const assertApi = async (key: string) => {
    const expected = fixture.expected[key];
    const params = query(expected.filters);
    const summary = await request.get(`${api}/pipeline/summary?${params}`, { headers });
    expect(summary.ok()).toBe(true);
    const totals = await summary.json();
    expect(totals.open_count).toBe(expected.total);
    expect(totals.open_value_by_currency).toEqual(expected.currency_totals);
    const clients = await request.get(`${api}/pipeline/clients?${params}&page_size=25`, { headers });
    expect(clients.ok()).toBe(true);
    const accounts = await clients.json();
    expect(accounts.total).toBe(expected.clients.length);
    expect(accounts.items.map((r: any) => [r.client_id, r.matching_deal_count]).sort()).toEqual(expected.clients.map((r: any) => [r.id, r.matching_deal_count]).sort());
  };
  const visibleIds = () => page.locator('[data-testid^="opp-row-"]').evaluateAll(rows => rows.map(row => row.getAttribute("data-testid")!.replace("opp-row-", "")));
  const expectPage = async (ids: string[]) => {
    await expect(page.getByTestId("page-size")).toBeVisible();
    await expect.poll(visibleIds).toEqual(ids);
  };
  await page.goto("/pipeline?view=opportunities&sort=client_name");
  await expect(page.getByRole("tab", { name: "Opportunities (88)", exact: true })).toBeVisible();
  await page.getByTestId("filter-owner").selectOption(selected.filters.owner[0]);
  await page.getByTestId("filter-business-unit").selectOption("consulting");
  await page.getByTestId(`stage-chip-${selected.filters.stage[0]}`).click();
  await expect(page.getByRole("tab", { name: "Opportunities (64)", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Clients (16 matching)", exact: true })).toBeVisible();
  await expect(page.getByTestId(`stage-chip-count-${selected.filters.stage[0]}`)).toHaveText("64");
  await expect(page.getByTestId(`stage-chip-value-${selected.filters.stage[0]}`)).toContainText("64,000");
  await expect(page.getByTestId("summary-bar")).toContainText("64,000");
  await assertApi("selected");
  for (let i = 0; i < selected.pages_25.length; i++) {
    await expectPage(selected.pages_25[i]);
    if (i + 1 < selected.pages_25.length) await page.getByTestId("page-next").click();
  }
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export filtered CSV" }).click();
  const download = await downloadEvent;
  const csvPath = testInfo.outputPath("selected.csv");
  await download.saveAs(csvPath);
  expect(await download.failure()).toBeNull();
  const root = resolve(process.cwd(), "../..");
  const csv = JSON.parse(execFileSync(`${root}/api/.venv/bin/python`, ["-c", "import csv,json,sys; print(json.dumps(list(csv.DictReader(open(sys.argv[1], newline='')))))", csvPath], { encoding: "utf8" }));
  expect(csv[0].deal).toContain("64 matching");
  expect(csv[0].deal).toContain("64000.00 USD");
  expect(csv.slice(1).map((r: any) => r.deal).sort()).toEqual(fixture.fixture_rows.filter((r: any) => selected.ids.includes(r.id)).map((r: any) => r.name).sort());
  expect(csv.slice(1).every((r: any) => r.amount === "1000.00" && r.currency === "USD")).toBe(true);
  const thirdPageUrl = page.url();
  await page.reload();
  await expectPage(selected.pages_25[2]);
  await page.getByTestId(`opp-row-${selected.pages_25[2][0]}`).click();
  await expect(page).toHaveURL(/\/deals\//);
  await page.goBack();
  await expect(page).toHaveURL(thirdPageUrl);
  await expectPage(selected.pages_25[2]);
  await page.getByRole("button", { name: "Remove BU: consulting", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Opportunities (72)", exact: true })).toBeVisible();
  expect(new URL(page.url()).searchParams.get("owner")).toBe(selected.filters.owner[0]);
  expect(new URL(page.url()).searchParams.get("stage")).toBe(selected.filters.stage[0]);
  await assertApi("owner_stage");
  await page.getByTestId("filter-saved-view").selectOption(fixture.stage_only_saved_view_id);
  await expect(page.getByRole("tab", { name: "Opportunities (8)", exact: true })).toBeVisible();
  expect(new URL(page.url()).searchParams.has("owner")).toBe(false);
  expect(new URL(page.url()).searchParams.has("business_unit")).toBe(false);
  await expectPage(fixture.expected.stage_only_saved.ids);
  await page.reload();
  await expectPage(fixture.expected.stage_only_saved.ids);
  await assertApi("stage_only_saved");
  await page.goto(`/pipeline?view=opportunities&${query(fixture.expected.zero.filters)}`);
  await expect(page.getByRole("tab", { name: "Opportunities (0)", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Clients (0 matching)", exact: true })).toBeVisible();
  await expect(page.locator('[data-testid^="opp-row-"]')).toHaveCount(0);
  await assertApi("zero");
  await page.goto("/pipeline?view=opportunities&sort=client_name");
  await expect(page.getByRole("tab", { name: "Opportunities (88)", exact: true })).toBeVisible();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const held = new Set<string>();
  await page.route("**/api/pipeline/**", async route => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("search") !== "Synthetic T09 Deal 00" || url.searchParams.has("watching") || !["/api/pipeline/opportunities", "/api/pipeline/clients", "/api/pipeline/summary"].includes(url.pathname)) {
      await route.continue({ headers: { ...route.request().headers(), ...headers } });
      return;
    }
    const response = await route.fetch({ headers: { ...route.request().headers(), ...headers } });
    expect(response.ok()).toBe(true);
    const payload = await response.json();
    if (url.pathname.endsWith("/opportunities")) {
      expect(payload.total).toBe(10);
      expect(payload.items.map((row: any) => row.opportunity_id).sort()).toEqual(fixture.fixture_rows.filter((row: any) => row.index < 10).map((row: any) => row.id).sort());
    } else if (url.pathname.endsWith("/clients")) {
      expect(payload.total).toBe(3);
      expect(payload.items.map((row: any) => row.matching_deal_count).sort()).toEqual([2, 4, 4]);
    } else {
      expect(payload.open_count).toBe(10);
      expect(payload.open_value_by_currency).toEqual({ USD: "10000.00" });
    }
    held.add(url.pathname);
    await gate;
    await route.fulfill({ response });
  });
  try {
    const search = page.getByRole("searchbox", { name: "Search deal or client", exact: true });
    await search.fill("Synthetic T09 Deal 00");
    await search.press("Enter");
    await expect.poll(() => held.size).toBe(3);
    await search.fill("no-synthetic-match");
    await search.press("Enter");
    await expect(page.getByRole("tab", { name: "Opportunities (0)", exact: true })).toBeVisible();
    const oldResponses = [...held].map(path => page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === path && url.searchParams.get("search") === "Synthetic T09 Deal 00" && !url.searchParams.has("watching");
    }));
    release();
    for (const pending of oldResponses) expect(await (await pending).finished()).toBeNull();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.locator('[data-testid^="opp-row-"]')).toHaveCount(0);
    await expect(page.getByRole("tab", { name: "Clients (0 matching)", exact: true })).toBeVisible();
    await expect(page.getByTestId("summary-bar").getByText("Open deals", { exact: true }).locator("..").locator("div").last()).toHaveText("0");
    await page.screenshot({ path: "../../docs/s21/evidence/baseline/t09-empty.png" });
  } finally {
    release();
  }
  await page.getByRole("tab", { name: "Clients (0 matching)", exact: true }).click();
  await page.getByRole("checkbox", { name: "Show clients with no match", exact: true }).check();
  const emptyDownloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export filtered CSV" }).click();
  const emptyDownload = await emptyDownloadEvent;
  const emptyPath = testInfo.outputPath("zero-with-client-display.csv");
  await emptyDownload.saveAs(emptyPath);
  expect(await emptyDownload.failure()).toBeNull();
  const emptyCsv = JSON.parse(execFileSync(`${root}/api/.venv/bin/python`, ["-c", "import csv,json,sys; print(json.dumps(list(csv.DictReader(open(sys.argv[1], newline='')))))", emptyPath], { encoding: "utf8" }));
  expect(emptyCsv).toHaveLength(1);
  expect(emptyCsv[0].deal).toContain("0 matching");
});
