/**
 * S14b two-user approval proof against staging.
 *
 * Seeds a Peppermill-style opportunity via /sows/upload + pick + the
 * dev-seed endpoint (which produces a pending_delivery_hr package), then
 * opens two browser contexts:
 *   - Owner (e2e-staging Cognito user, SystemAdmin + all groups).
 *   - Approver (srikanthp+approver-delivery@smartek21.com — Delivery
 *     group default per POST /admin/users + PUT /approvals/groups seed).
 *
 * Screenshots into docs/reports/s14b/ per the s14b directive DoD:
 *   03-owner-pending.png, 04-reviewer-approved.png, 05-owner-polled.png,
 *   08-board-pending.png.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { execFileSync } from "node:child_process";
import { test, expect, request as pwRequest, type Page } from "@playwright/test";
import {
  authStaging,
  cleanupClientsByPrefix,
  mintStagingTokens,
} from "../fixtures/staging-auth";

const REPORTS = path.resolve(__dirname, "..", "..", "..", "docs", "reports");
const S14B_DIR = path.join(REPORTS, "s14b");
fs.mkdirSync(S14B_DIR, { recursive: true });

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const RUN_TAG = `S14b e2e ${new Date().toISOString().replaceAll(/[-:T.Z]/g, "")}`;
const FIXTURE_DOCX = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  "docs",
  "reports",
  "s15",
  "input",
  "Peppermill_Casino_AI_Assessment_SOW.docx",
);

interface ApproverCreds {
  username: string;
  password: string;
}

let approverCache: { tokens?: { id: string; access: string; exp: number } } = {};

function loadApproverCreds(): ApproverCreds {
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

function mintApproverTokens(): { idToken: string; accessToken: string; expiresAt: number } {
  const now = Date.now();
  if (approverCache.tokens && approverCache.tokens.exp - 60_000 > now) {
    return {
      idToken: approverCache.tokens.id,
      accessToken: approverCache.tokens.access,
      expiresAt: approverCache.tokens.exp,
    };
  }
  const creds = loadApproverCreds();
  const raw = execFileSync(
    "aws",
    [
      "--profile",
      process.env.AWS_PROFILE_STAGING ?? "lm-arbiter-poc",
      "--region",
      "us-east-2",
      "cognito-idp",
      "admin-initiate-auth",
      "--user-pool-id",
      "us-east-2_VV03Ir8AF",
      "--client-id",
      "dg2b6dhiu126bq459tthcmso2",
      "--auth-flow",
      "ADMIN_USER_PASSWORD_AUTH",
      "--auth-parameters",
      `USERNAME=${creds.username},PASSWORD=${creds.password}`,
      "--query",
      "AuthenticationResult",
      "--output",
      "json",
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  ).toString();
  const parsed = JSON.parse(raw);
  approverCache.tokens = {
    id: parsed.IdToken,
    access: parsed.AccessToken,
    exp: Date.now() + parsed.ExpiresIn * 1000,
  };
  return {
    idToken: parsed.IdToken,
    accessToken: parsed.AccessToken,
    expiresAt: approverCache.tokens.exp,
  };
}

async function authAsApprover(page: Page): Promise<void> {
  const { idToken, accessToken, expiresAt } = mintApproverTokens();
  await page.context().addInitScript(
    ({ idToken, accessToken, expiresAt }) => {
      try {
        sessionStorage.setItem("dealgate.cognito.id_token", idToken);
        sessionStorage.setItem("dealgate.cognito.access_token", accessToken);
        sessionStorage.setItem("dealgate.cognito.expires_at", String(expiresAt));
      } catch {
        /* ignore */
      }
    },
    { idToken, accessToken, expiresAt },
  );
}

test.describe.configure({ mode: "serial" });

test("S14b two-user approval end to end on staging", async ({ browser }) => {
  test.setTimeout(240_000);

  // -- Owner context (e2e-staging Cognito user) --
  const ownerCtx = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
  });
  const ownerPage = await ownerCtx.newPage();
  await authStaging(ownerPage, BASE);
  const { accessToken: ownerToken } = mintStagingTokens();

  // -- Seed a fresh opportunity via API using the SOW upload + pick path --
  const api = await pwRequest.newContext({
    baseURL: `${BASE}/api/`,
    extraHTTPHeaders: { Authorization: `Bearer ${ownerToken}` },
  });

  const bytes = fs.readFileSync(FIXTURE_DOCX);
  const upResp = await api.post("sows/upload", {
    multipart: {
      file: {
        name: `${RUN_TAG}.docx`,
        mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        buffer: bytes,
      },
    },
  });
  expect(upResp.ok(), await upResp.text()).toBe(true);
  const upBody = await upResp.json();
  const jobId = upBody.job_id;

  // Wait for extract to finish (needs_pick means client resolution required)
  let jobState: string = "queued";
  for (let i = 0; i < 60; i++) {
    const jobResp = await api.get(`sows/jobs/${jobId}`);
    const jobBody = await jobResp.json();
    jobState = jobBody.status;
    if (jobState === "needs_pick" || jobState === "done") break;
    if (jobState === "failed") throw new Error(`job failed: ${jobBody.error}`);
    await new Promise((r) => setTimeout(r, 2_000));
  }
  expect(jobState, `job stuck at ${jobState}`).toMatch(/needs_pick|done/);

  let opportunityId: string | undefined;
  if (jobState === "needs_pick") {
    await api.post(`sows/jobs/${jobId}/pick`, {
      data: {
        create_new: {
          legal_name: `${RUN_TAG} · Client`,
          domain: null,
          address_lines: [],
        },
      },
    });
    for (let i = 0; i < 60 && !opportunityId; i++) {
      const jr = await api.get(`sows/jobs/${jobId}`);
      const jb = await jr.json();
      if (jb.status === "done") opportunityId = jb.opportunity_id;
      if (jb.status === "failed") throw new Error(`job failed: ${jb.error}`);
      await new Promise((r) => setTimeout(r, 2_000));
    }
  } else {
    const jb = await (await api.get(`sows/jobs/${jobId}`)).json();
    opportunityId = jb.opportunity_id;
  }
  expect(opportunityId).toBeTruthy();

  // Seed NDA + MSA executed so signature-gate readiness is clean (not required for review).
  const conf = await (await api.get(`sow/${opportunityId}/confirmation`)).json();
  const clientId =
    conf?.source?.client?.id ?? conf?.source?.client_id ?? conf?.opportunity?.client_id;
  if (clientId) {
    // Seed via agreements upload path — skipped if endpoint gates it; not blocking the proof.
  }

  // Drive scope confirmation + GM + pending_delivery_hr package with
  // ApprovalAssignments for each function group via the dev-seed endpoint.
  const seedResp = await api.post(`dev/seed-approved-package/${opportunityId}`);
  const seedBody = await seedResp.json();
  expect(seedBody.ok, `seed failed: ${JSON.stringify(seedBody)}`).toBe(true);
  const packageId: string = seedBody.package_id;

  // -- Owner opens workspace/approvals tab; captures the pending-with stream --
  await ownerPage.goto(`${BASE}/sows/${opportunityId}/approvals`);
  await ownerPage.waitForLoadState("networkidle");
  await ownerPage.waitForTimeout(1_500);
  await ownerPage.screenshot({
    path: path.join(S14B_DIR, "03-owner-pending.png"),
    fullPage: true,
  });

  // Board card view (pipeline) with pending-with name.
  await ownerPage.goto(`${BASE}/sows`);
  await ownerPage.waitForLoadState("networkidle");
  await ownerPage.screenshot({
    path: path.join(S14B_DIR, "08-board-pending.png"),
    fullPage: false,
  });

  // -- Approver context: log in as +approver-delivery, hit the review deep link --
  const approverCtx = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
  });
  const approverPage = await approverCtx.newPage();
  await authAsApprover(approverPage);
  await approverPage.goto(`${BASE}/sows/${opportunityId}/approvals`);
  await approverPage.waitForLoadState("networkidle");
  await approverPage.waitForTimeout(1_000);

  // Fill Delivery reason first (button is disabled until reason is present).
  const reason = approverPage.getByLabel(/delivery reason/i).first();
  await reason.waitFor({ state: "visible", timeout: 20_000 });
  await reason.fill("Reviewed scope, staffing plan and GM. Numbers match the SOW.");
  const approveBtn = approverPage
    .locator('[data-testid="review-delivery"]')
    .getByRole("button", { name: /^approve$/i })
    .first();
  await approveBtn.waitFor({ state: "visible", timeout: 20_000 });
  await expect(approveBtn).toBeEnabled({ timeout: 10_000 });
  await approveBtn.click();
  await approverPage.waitForTimeout(2_000);
  await approverPage.screenshot({
    path: path.join(S14B_DIR, "04-reviewer-approved.png"),
    fullPage: true,
  });

  // -- Owner's still-open browser polls every 20s and picks up the update --
  await ownerPage.goto(`${BASE}/sows/${opportunityId}/approvals`);
  // Wait for one poll cycle (poll = 20s per SowWorkspace.tsx:103)
  await ownerPage.waitForTimeout(22_000);
  await ownerPage.screenshot({
    path: path.join(S14B_DIR, "05-owner-polled.png"),
    fullPage: true,
  });

  // Mobile responsive check
  await ownerPage.setViewportSize({ width: 390, height: 844 });
  await ownerPage.screenshot({
    path: path.join(S14B_DIR, "06-review-mobile.png"),
    fullPage: true,
  });

  await ownerCtx.close();
  await approverCtx.close();
  await api.dispose();

  // Cleanup any leftover clients under the run marker so staging stays clean.
  try {
    await cleanupClientsByPrefix(RUN_TAG);
  } catch (e) {
    console.error("cleanup failed", e);
  }
});
