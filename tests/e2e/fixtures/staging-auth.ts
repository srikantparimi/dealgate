/**
 * Staging Cognito auth for Playwright (S12).
 *
 * Mints a real Cognito token via `admin_initiate_auth` and injects it into
 * the browser's sessionStorage under the same keys the app reads
 * (`dealgate.cognito.*`). The test user + password live in AWS Secrets
 * Manager (`officeapp-dev-e2e-user`); never in the repo, never in an env
 * var, never printed to the log.
 *
 * The test user is a member of the dedicated `officeapp-e2e` Cognito
 * group — plus every governance group needed to drive the 8-step proof
 * (Sales / Delivery / Finance / Legal / CEO / SalesLeader / SystemAdmin).
 * Rotate the password via `aws secretsmanager put-secret-value` +
 * `aws cognito-idp admin-set-user-password`; nothing else in the codebase
 * cares which value it is.
 */
import { execFileSync } from "node:child_process";
import type { Page } from "@playwright/test";

interface StagingCreds {
  user_pool_id: string;
  client_id: string;
  username: string;
  password: string;
  region: string;
}

interface AuthResult {
  IdToken: string;
  AccessToken: string;
  ExpiresIn: number;
}

let cachedTokens: {
  fetchedAt: number;
  expiresAt: number;
  idToken: string;
  accessToken: string;
} | null = null;

function awsCli(args: string[]): string {
  const out = execFileSync("aws", args, {
    stdio: ["ignore", "pipe", "pipe"],
    env: process.env,
  });
  return out.toString().trim();
}

function loadCreds(): StagingCreds {
  const profile = process.env.AWS_PROFILE_STAGING ?? "lm-arbiter-poc";
  const secretId = process.env.STAGING_E2E_SECRET ?? "officeapp-dev-e2e-user";
  const region = process.env.STAGING_E2E_REGION ?? "us-east-2";
  const raw = awsCli([
    "--profile",
    profile,
    "--region",
    region,
    "secretsmanager",
    "get-secret-value",
    "--secret-id",
    secretId,
    "--query",
    "SecretString",
    "--output",
    "text",
  ]);
  return JSON.parse(raw) as StagingCreds;
}

/**
 * Mint fresh Cognito tokens. Cached within the process until 60s before
 * expiry so a slow suite doesn't hit the auth endpoint before every spec.
 */
export function mintStagingTokens(): { idToken: string; accessToken: string; expiresAt: number } {
  const now = Date.now();
  if (cachedTokens && cachedTokens.expiresAt - 60_000 > now) {
    return {
      idToken: cachedTokens.idToken,
      accessToken: cachedTokens.accessToken,
      expiresAt: cachedTokens.expiresAt,
    };
  }
  const creds = loadCreds();
  const profile = process.env.AWS_PROFILE_STAGING ?? "lm-arbiter-poc";
  const raw = awsCli([
    "--profile",
    profile,
    "--region",
    creds.region,
    "cognito-idp",
    "admin-initiate-auth",
    "--user-pool-id",
    creds.user_pool_id,
    "--client-id",
    creds.client_id,
    "--auth-flow",
    "ADMIN_USER_PASSWORD_AUTH",
    "--auth-parameters",
    `USERNAME=${creds.username},PASSWORD=${creds.password}`,
    "--query",
    "AuthenticationResult",
    "--output",
    "json",
  ]);
  const auth = JSON.parse(raw) as AuthResult;
  const expiresAt = now + auth.ExpiresIn * 1000;
  cachedTokens = {
    fetchedAt: now,
    expiresAt,
    idToken: auth.IdToken,
    accessToken: auth.AccessToken,
  };
  return { idToken: auth.IdToken, accessToken: auth.AccessToken, expiresAt };
}

/**
 * Attach fresh Cognito tokens to `page` before it navigates to the app.
 *
 * The frontend reads its tokens from sessionStorage on load
 * (`web/src/auth/cognito.ts`). If we let the app load first it redirects
 * to the Cognito hosted UI (destroying our page evaluate context), so we
 * inject the tokens via `addInitScript` — that runs at document-start of
 * every navigation, before any app code sees the empty storage.
 */
export async function authStaging(page: Page, _baseUrl: string): Promise<void> {
  const { idToken, accessToken, expiresAt } = mintStagingTokens();
  await page.context().addInitScript(
    ({ idToken, accessToken, expiresAt }) => {
      try {
        sessionStorage.setItem("dealgate.cognito.id_token", idToken);
        sessionStorage.setItem("dealgate.cognito.access_token", accessToken);
        sessionStorage.setItem("dealgate.cognito.expires_at", String(expiresAt));
      } catch {
        /* opaque origins have no sessionStorage; ignore */
      }
    },
    { idToken, accessToken, expiresAt },
  );
}
