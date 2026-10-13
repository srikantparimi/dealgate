import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";


const actor = "command-center-owner@example.test";
const apiBase = process.env.COMMAND_CENTER_API_URL ?? "http://127.0.0.1:8230";
const evidence = resolve(
  process.cwd(),
  "../../docs/evidence/command-center",
);

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) =>
    route.continue({
      headers: { ...route.request().headers(), "x-test-user": actor },
    }),
  );
});

test("Stage 5 scope, financial separation, filters and drawer work together", async ({
  page,
  request,
}) => {
  const response = await request.get(`${apiBase}/command-center/accounts`, {
    headers: { "X-Test-User": actor },
  });
  expect(response.status()).toBe(200);
  const accounts = await response.json();
  expect(accounts.items.map((row: { account_name: string }) => row.account_name)).toEqual([
    "Stage Five Account",
    "Stage Six Account",
  ]);
  expect(new Set(accounts.items.map((row: { opportunity_id: string }) => row.opportunity_id)).size).toBe(2);
  const stageFive = accounts.items.find(
    (row: { account_name: string }) => row.account_name === "Stage Five Account",
  );
  expect(stageFive).toBeTruthy();

  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/command");
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  await expect(page.getByTestId("stage5-scope")).toHaveText(
    "HubSpot deals · Stage 5 and above",
  );
  await expect(
    page.getByText("Open late-stage work, current-period wins and active delivery."),
  ).toBeVisible();
  const table = page.getByRole("table");
  await expect(table).toContainText("Stage Five Account");
  await expect(table).toContainText("Stage Six Account");
  await expect(table).not.toContainText("Stage Four Account");
  await expect(table).not.toContainText("Historical Won Account");

  const outlook = page.getByRole("region", { name: "Revenue outlook" });
  await expect(outlook).toContainText("$90,000");
  await expect(outlook).toContainText("$224,000");
  await expect(page.getByText("62.5%", { exact: true }).first()).toBeVisible();

  await page.getByLabel("Business unit").selectOption("ST21");
  await expect(page).toHaveURL(/bu=ST21/);
  await expect(page.getByRole("button", { name: "ST21" })).toBeVisible();
  await page.getByRole("button", { name: "Reset user filters" }).click();
  await expect(page).not.toHaveURL(/bu=ST21/);
  await expect(page.getByTestId("stage5-scope")).toBeVisible();

  await page.getByLabel("Account owner").selectOption({ label: "Command Owner" });
  await expect(page).toHaveURL(/owner=/);
  await expect(table).toContainText("Stage Five Account");
  await page.getByRole("button", { name: "Reset user filters" }).click();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export this view" }).click();
  expect((await download).suggestedFilename()).toBe("dealgate-command-center.csv");

  await page.getByRole("button", { name: "Stage Five Account" }).click();
  const drawer = page.getByRole("dialog", { name: "Stage Five Account" });
  await expect(drawer).toContainText("Stage Five signed delivery");
  await expect(drawer.getByRole("link", { name: "Open deal" })).toHaveAttribute(
    "href",
    `/deals/${stageFive.opportunity_id}`,
  );
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible();

  mkdirSync(evidence, { recursive: true });
  await page.screenshot({
    path: resolve(evidence, "command-center-desktop.png"),
    fullPage: true,
  });
});

test("mobile layout contains wide data surfaces without widening the page", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/command");
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  await expect(page.getByTestId("stage5-scope")).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    )
    .toBe(true);

  mkdirSync(evidence, { recursive: true });
  await page.screenshot({
    path: resolve(evidence, "command-center-mobile.png"),
    fullPage: true,
  });
});
