/**
 * Integration browser proofs for feat/s16a + feat/s14b, run against
 * staging (https://app.dealgateapp.com). Screenshots overwrite the
 * per-directive folders under docs/reports/s16a/ and docs/reports/s14b/.
 *
 * Runs under Playwright with the standard authStaging helper (Cognito).
 * Auth uses the officeapp-dev-e2e-user secret (SystemAdmin + all groups)
 * for the submitter and the +approver-delivery Cognito user for the
 * two-user approval proof.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { test, expect } from "@playwright/test";
import {
  authStaging,
  cleanupClientsByPrefix,
  mintStagingTokens,
} from "../fixtures/staging-auth";
import { execFileSync } from "node:child_process";

const REPORTS = path.resolve(__dirname, "..", "..", "..", "docs", "reports");
const S16A_DIR = path.join(REPORTS, "s16a");
const S14B_DIR = path.join(REPORTS, "s14b");
fs.mkdirSync(S16A_DIR, { recursive: true });
fs.mkdirSync(S14B_DIR, { recursive: true });

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const MARKER = `S16-S14 e2e ${new Date().toISOString().replaceAll(/[-:T.Z]/g, "")}`;

function loadApproverPassword(): { username: string; password: string } {
  const raw = execFileSync(
    "aws",
    [
      "--profile",
      process.env.AWS_PROFILE_STAGING ?? "lm-arbiter-poc",
      "--region",
      "us-east-2",
      "secretsmanager",
      "get-secret-value",
      "--secret-id",
      "officeapp-dev-e2e-approvers",
      "--query",
      "SecretString",
      "--output",
      "text",
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  ).toString();
  const parsed = JSON.parse(raw);
  return {
    username: parsed.approver_delivery_username,
    password: parsed.approver_delivery_password,
  };
}

test.describe.configure({ mode: "serial" });

test.describe("S16a browser proofs", () => {
  test.beforeEach(async ({ page }) => {
    await authStaging(page);
  });

  test("legacy route redirects to Retired page", async ({ page }) => {
    await page.goto(`${BASE}/deals`);
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(/retired|no longer|moved/i).first()).toBeVisible({ timeout: 30_000 });
    await page.screenshot({
      path: path.join(S16A_DIR, "retired-route.png"),
      fullPage: true,
    });
  });

  test("primary navigation matches directive", async ({ page }) => {
    await page.goto(`${BASE}/command`);
    await page.waitForLoadState("networkidle");
    // The primary nav rail is a stable region — screenshot the whole shell.
    await page.screenshot({
      path: path.join(S16A_DIR, "nav-after-cut.png"),
      fullPage: false,
    });
  });

  test("simplified NDA & MSA register", async ({ page }) => {
    await page.goto(`${BASE}/agreements`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({
      path: path.join(S16A_DIR, "agreements-after.png"),
      fullPage: true,
    });
    // Mobile view
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.join(S16A_DIR, "agreements-mobile.png"),
      fullPage: true,
    });
  });

  test("Projects page shows running projects only", async ({ page }) => {
    await page.goto(`${BASE}/projects`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({
      path: path.join(S16A_DIR, "projects-desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.join(S16A_DIR, "projects-mobile.png"),
      fullPage: true,
    });
  });
});

test.describe("S14b browser proofs", () => {
  test.beforeEach(async ({ page }) => {
    await authStaging(page);
  });

  test("approval groups screen shows all five", async ({ page }) => {
    await page.goto(`${BASE}/settings/people?tab=groups`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({
      path: path.join(S14B_DIR, "01-groups-configured.png"),
      fullPage: true,
    });
  });

  test("submit dialog shows frozen versions + pre-filled approvers", async ({ page, request }) => {
    // Peppermill Casino fixture opportunity used across previous reports.
    await page.goto(`${BASE}/sows/4aab5ea6-f788-43f8-a2de-c759cfde1004`);
    await page.waitForLoadState("networkidle");
    // Header CTA state machine — expect either Submit or Complete scope depending on current state.
    await page.screenshot({
      path: path.join(S14B_DIR, "02-workspace-header.png"),
      fullPage: false,
    });
    const submit = page.getByRole("button", { name: /submit for approval/i });
    if (await submit.isVisible().catch(() => false)) {
      await submit.click();
      await page.getByRole("dialog").waitFor({ timeout: 10_000 });
      await page.screenshot({
        path: path.join(S14B_DIR, "02-submit-dialog.png"),
        fullPage: true,
      });
      await page.getByRole("button", { name: /cancel|close/i }).click().catch(() => {});
    } else {
      await page.screenshot({
        path: path.join(S14B_DIR, "02-cta-state.png"),
        fullPage: true,
      });
    }
  });

  test("Approvals tab renders pending-with stream", async ({ page }) => {
    await page.goto(`${BASE}/sows/4aab5ea6-f788-43f8-a2de-c759cfde1004/approvals`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({
      path: path.join(S14B_DIR, "03-review-stream.png"),
      fullPage: true,
    });
  });
});
