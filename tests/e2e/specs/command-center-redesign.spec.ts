import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

import { authStaging, mintStagingTokens } from "../fixtures/staging-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const evidence = resolve(process.cwd(), "../../docs/evidence/command-center");

type AccountRow = {
  opportunity_id: string;
  hubspot_deal_id: string;
  account_name: string;
};

type AccountsPage = {
  items: AccountRow[];
  total: number;
  page: number;
  page_size: number;
  scope_label: string;
  configuration_gaps: string[];
};

type CommandOverview = {
  tiles: Record<string, unknown>;
  actions: unknown[];
  brief: unknown[];
  revenue: { months: unknown[] };
  lifecycle_items: Array<{ key: string }>;
  capacity: { month: string; status: string };
  sources: Array<{ name: string; status: string }>;
};

test.beforeEach(async ({ page }) => {
  await authStaging(page, BASE);
});

test("deployed Command Center serves the canonical scope and connected operations", async ({
  page,
  request,
}) => {
  const { idToken } = mintStagingTokens();
  const headers = { Authorization: `Bearer ${idToken}` };
  const [accountsResponse, overviewResponse] = await Promise.all([
    request.get(`${BASE}/api/command-center/accounts?page_size=100`, { headers }),
    request.get(`${BASE}/api/command-center/overview`, { headers }),
  ]);
  expect(accountsResponse.status()).toBe(200);
  expect(overviewResponse.status()).toBe(200);

  const accounts = (await accountsResponse.json()) as AccountsPage;
  const overview = (await overviewResponse.json()) as CommandOverview;
  expect(accounts.scope_label).toBe("HubSpot deals · Stage 5 and above");
  expect(accounts.configuration_gaps).toEqual(expect.any(Array));
  expect(Object.keys(overview.tiles).sort()).toEqual(
    ["backlog", "gm", "people", "pipeline", "revenue"],
  );
  expect(overview.brief).toHaveLength(3);
  expect(overview.revenue.months).toHaveLength(3);
  expect(overview.lifecycle_items.map((item) => item.key)).toEqual([
    "pipeline",
    "sow_in_approval",
    "signed",
    "engagement_created",
    "active",
    "renewal_due",
  ]);
  expect(overview.capacity.month).toMatch(/^\d{4}-\d{2}$/);
  expect(overview.sources.map((source) => source.name)).toEqual(
    expect.arrayContaining([
      "Portfolio engagement ledger",
      "Forecast calculation service",
      "Workforce supply",
      "HubSpot pipeline mirror",
    ]),
  );
  expect(new Set(accounts.items.map((row) => row.opportunity_id)).size).toBe(
    accounts.items.length,
  );
  for (const row of accounts.items) {
    expect(row.opportunity_id).toMatch(/^[0-9a-f-]{36}$/i);
    expect(row.hubspot_deal_id).not.toBe("");
  }

  const accountLoad = page.waitForResponse(
    (response) =>
      response.url().includes("/api/command-center/accounts?") &&
      response.request().method() === "GET",
  );
  const overviewLoad = page.waitForResponse(
    (response) =>
      response.url().includes("/api/command-center/overview?") &&
      response.request().method() === "GET",
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${BASE}/command`);
  expect((await accountLoad).status()).toBe(200);
  expect((await overviewLoad).status()).toBe(200);

  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  await expect(page.getByTestId("stage5-scope")).toHaveText(
    "HubSpot deals · Stage 5 and above",
  );
  await expect(page.getByRole("heading", { name: "Business now" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Needs attention" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Three facts to act on" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "From opportunity to delivery" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Revenue outlook" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Capacity by location" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Accounts & engagements" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Data & operational health" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Filter accounts by business unit" })).toBeVisible();
  await expect(page.getByText(/Could not load (actions|accounts):/)).toHaveCount(0);
  for (const label of [
    "Revenue this month",
    "GM this month",
    "Signed backlog",
    "Weighted pipeline",
    "People",
  ]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText("Unknown", { exact: true })).toHaveCount(0);

  for (const label of ["Pipeline", "SOWs & approvals", "Projects", "Forecast", "Portfolio", "People"]) {
    await expect(
      page.getByLabel("Primary navigation").getByRole("link", { name: label, exact: true }),
    ).toBeVisible();
  }

  if (accounts.items.length === 0) {
    await expect(
      page.getByText("No current Stage 5 or later HubSpot deals match these filters."),
    ).toBeVisible();
    await expect(page.getByText("0 eligible deals")).toBeVisible();
  } else {
    const first = accounts.items[0];
    await page.getByRole("button", { name: first.account_name }).first().click();
    const drawer = page.getByRole("dialog", { name: first.account_name });
    await expect(drawer.getByText("HubSpot deal · Stage 5+")).toBeVisible();
    await expect(drawer.getByRole("link", { name: "Open deal" })).toHaveAttribute(
      "href",
      `/deals/${first.opportunity_id}`,
    );
    await page.keyboard.press("Escape");
    await expect(drawer).not.toBeVisible();
  }

  await page.getByLabel("Financial period").selectOption("next_two_quarters");
  await expect(page).toHaveURL(/period=next_two_quarters/);
  await expect(page.getByRole("button", { name: "Reset user filters" })).toBeVisible();
  await page.getByRole("button", { name: "Reset user filters" }).click();
  await expect(page).not.toHaveURL(/period=next_two_quarters/);
  await expect(page.getByTestId("stage5-scope")).toBeVisible();

  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export this view" }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("dealgate-command-center.csv");
  const csvPath = await download.path();
  expect(csvPath).not.toBeNull();
  const csv = readFileSync(csvPath!, "utf8");
  expect(csv.split("\n")[0]).toContain("HubSpot deal");
  expect(csv.split("\n")[0]).toContain("Forecast GM");

  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeInViewport();
  mkdirSync(evidence, { recursive: true });
  await page.screenshot({
    path: resolve(evidence, "command-center-staging-desktop.png"),
  });
});

test("deployed Command Center contains every surface at mobile width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE}/command`);
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  await expect(page.getByTestId("stage5-scope")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Business now" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Three facts to act on" })).toBeVisible();
  await expect(page.getByText(/^\d+ eligible deals?$/)).toBeVisible();
  await expect(page.getByText("Loading business evidence…")).toHaveCount(0);
  await expect(page.getByText("Loading eligible HubSpot deals…")).toHaveCount(0);
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    )
    .toBe(true);

  mkdirSync(evidence, { recursive: true });
  await page.screenshot({
    path: resolve(evidence, "command-center-staging-mobile.png"),
    fullPage: true,
  });
});
