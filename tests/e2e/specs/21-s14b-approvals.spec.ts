import { test, expect, type BrowserContext } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";

const opportunity = "14140000-0000-0000-0000-000000000001";
const below = "14140000-0000-0000-0000-000000000002";
const screenshots = path.resolve(__dirname, "../../../docs/reports/s14b");

async function identity(context: BrowserContext, actor: string) {
  await context.addInitScript(actor => {
    // UI-only local fixture claims; server identity still comes from the guarded fixture dependency.
    const groups = actor === "owner" ? ["SystemAdmin", "Sales"] : ["Delivery"];
    sessionStorage.setItem("dealgate.cognito.id_token", `local.${btoa(JSON.stringify({ sub: actor, email: `s14b-${actor}@example.test`, name: actor, "cognito:groups": groups }))}.local`);
  }, actor);
  await context.route("http://127.0.0.1:8025/**", route => route.continue({ headers: { ...route.request().headers(), "x-test-user": `s14b-${actor}@example.test` } }));
}

test("S14b groups, scope, submission, two-user polling and CEO row", async ({ page, browser }) => {
  test.skip(!process.env.S14B_LOCAL_PROOF, "Requires disposable s14b_local.py server");
  test.setTimeout(180_000);
  fs.mkdirSync(screenshots, { recursive: true });
  await identity(page.context(), "owner");
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/settings/people?tab=groups");
  const delivery = page.getByRole("region", { name: "Delivery group", exact: true });
  await expect(delivery.getByLabel("Delivery default approver")).toBeVisible();
  await delivery.getByLabel("Delivery default approver").selectOption({ label: "Dana Delivery" });
  await delivery.getByRole("button", { name: "Save Delivery" }).click();
  await expect(delivery.getByRole("status")).toHaveText("Saved");
  const legal = page.getByRole("region", { name: "Legal group", exact: true });
  await legal.getByRole("checkbox", { name: "Lee Legal", exact: true }).uncheck();
  await legal.getByRole("button", { name: "Save Legal" }).click();
  await expect(legal.getByText(/Empty group/)).toBeVisible();
  await page.screenshot({ path: path.join(screenshots, "01-groups-empty-warning.png"), fullPage: true });
  await legal.getByRole("checkbox", { name: "Lee Legal", exact: true }).check();
  await legal.getByLabel("Legal default approver").selectOption({ label: "Lee Legal" });
  await legal.getByRole("button", { name: "Save Legal" }).click();
  await expect(legal.getByRole("status")).toHaveText("Saved");

  await page.goto(`/sows/${opportunity}/scope`);
  await expect(page.getByRole("button", { name: "Complete scope", exact: true })).toBeVisible();
  await expect(page.getByText("Scope draft", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Complete scope", exact: true }).click();
  await expect(page.getByTestId("confirmation-submit")).toBeEnabled();
  await page.getByTestId("confirmation-submit").click();
  await page.waitForURL(`**/sows/${opportunity}/approvals`);
  await expect(page.getByRole("button", { name: "Submit for approval", exact: true })).toBeEnabled();
  await expect(page.getByText("Scope confirmed", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Submit for approval", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(/Frozen package: SOW v1/)).toBeVisible();
  await expect(dialog.getByText(/submitter cannot approve/)).toBeVisible();
  await expect(dialog.getByLabel("Delivery approver").getByRole("option", { name: "Morgan Owner" })).toHaveCount(0);
  await page.screenshot({ path: path.join(screenshots, "02-submit-dialog.png"), fullPage: true });
  await dialog.getByRole("button", { name: "Confirm submission" }).click();
  await expect(page.getByRole("button", { name: "View review status", exact: true })).toBeVisible();
  await expect(page.getByTestId("review-delivery")).toContainText("Pending with Dana Delivery");
  await expect(page.getByText("NDA missing - blocks signature, not review.")).toBeVisible();
  await page.screenshot({ path: path.join(screenshots, "03-owner-pending.png"), fullPage: true });

  const other = await browser.newContext({ baseURL: process.env.E2E_BASE_URL, viewport: { width: 1440, height: 1100 } });
  await identity(other, "delivery");
  const reviewer = await other.newPage();
  await reviewer.goto("/work");
  await expect(reviewer.getByText("Delivery review", { exact: true }).first()).toBeVisible();
  await reviewer.getByText("Delivery review", { exact: true }).first().click();
  await reviewer.getByRole("link", { name: "Open workflow" }).click();
  await reviewer.waitForURL(`**/sows/${opportunity}/approvals`);
  const card = reviewer.getByTestId("review-delivery");
  await expect(card.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
  await card.getByLabel("Delivery reason").fill("Delivery scope, staffing and dates reviewed.");
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(reviewer.getByText("Delivery · Approved", { exact: true })).toBeVisible();
  await reviewer.screenshot({ path: path.join(screenshots, "04-reviewer-approved.png"), fullPage: true });
  await expect(page.getByText("Delivery · Approved", { exact: true })).toBeVisible({ timeout: 25_000 });
  await page.screenshot({ path: path.join(screenshots, "05-owner-polled.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(screenshots, "06-review-mobile.png"), fullPage: true });
  await other.close();

  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(`/sows/new?opportunityId=${below}`);
  await page.getByTestId("confirmation-submit").click();
  await page.getByRole("button", { name: "Submit for approval", exact: true }).click();
  await expect(page.getByRole("dialog").getByText(/CEO · Cameron CEO/)).toBeVisible();
  await page.screenshot({ path: path.join(screenshots, "07-below-floor-ceo.png"), fullPage: true });
  await page.getByRole("dialog").getByRole("button", { name: "Confirm submission" }).click();
  await expect(page.getByText(/CEO exception queued after functional reviews/)).toBeVisible();
});

test("S14b board and command center share pending names and routing blockers", async ({ page }) => {
  test.skip(!process.env.S14B_LOCAL_PROOF, "Requires the submitted local S14b fixture");
  test.setTimeout(90_000);
  await identity(page.context(), "owner");
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/sows");
  await expect(page.getByText(/Pending with Harper HR/).first()).toBeVisible();
  await page.screenshot({ path: path.join(screenshots, "08-board-pending.png"), fullPage: true });
  await page.goto("/settings/people?tab=groups");
  const legal = page.getByRole("region", { name: "Legal group", exact: true });
  await legal.getByRole("checkbox", { name: "Lee Legal", exact: true }).uncheck();
  await legal.getByRole("button", { name: "Save Legal" }).click();
  await expect(legal.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
  try {
    await page.goto("/");
    await expect(page.getByText(/Legal: no eligible reviewer. Owner: SystemAdmin/).first()).toBeVisible();
    await expect(page.getByText("GM v1 frozen").first()).toBeVisible();
    await expect(page.getByText("GM not built")).toHaveCount(0);
    await page.screenshot({ path: path.join(screenshots, "09-command-center-blocker.png"), fullPage: true });
  } finally {
    await page.goto("/settings/people?tab=groups");
    await legal.getByRole("checkbox", { name: "Lee Legal", exact: true }).check();
    await legal.getByLabel("Legal default approver").selectOption({ label: "Lee Legal" });
    await legal.getByRole("button", { name: "Save Legal" }).click();
    await expect(legal.getByRole("status")).toHaveText("Saved");
  }
});
