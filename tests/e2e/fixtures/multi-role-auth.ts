/**
 * Multi-role Cognito auth for Playwright (S20 · W5).
 *
 * `staging-auth.ts` mints one token for the SystemAdmin smoke bot. S20
 * needs a role-partitioned e2e story: one submitter, one delivery
 * reviewer, one HR, one Finance, one Legal, one CEO. This fixture
 * resolves each role by name to a Cognito user + password + tokens, and
 * offers an `actAs()` helper that swaps tokens on the Playwright page
 * without re-navigating.
 *
 * User inventory (see `docs/reports/s20/isolation.md` §Test-user tags):
 *
 * | Role slot   | Cognito username / email                            | Cognito groups (asserted server-side) |
 * | ---         | ---                                                 | ---                                   |
 * | `system`    | `e2e-staging@smartek21.com`                         | SystemAdmin + every governance group  |
 * | `submitter` | `e2e-staging@smartek21.com` (reused; owns intake)   | SystemAdmin + Sales                    |
 * | `delivery`  | `srikanthp+approver-delivery@smartek21.com`         | Delivery                              |
 * | `hr`        | `e2e-staging@smartek21.com` (reused for HR role)    | HR (via SystemAdmin envelope)         |
 * | `finance`   | `e2e-staging@smartek21.com` (reused for Finance)    | Finance                               |
 * | `legal`     | `e2e-staging@smartek21.com` (reused for Legal)      | Legal                                 |
 * | `ceo`       | `srikanthp+ceo@smartek21.com`                       | CEO, SystemAdmin                      |
 *
 * The reuse of `e2e-staging` for HR/Finance/Legal is intentional — the
 * isolation walkthrough (isolation.md) confirmed that Cognito pool
 * contains four users tonight. `e2e-staging` is a member of every
 * governance group, so it can drive HR/Finance/Legal requests via
 * the server's `require_role` guards. When separate role users get
 * provisioned in the morning, the mapping above is the one place that
 * needs to change — the callers use the role slot names, not the
 * emails.
 *
 * Secrets:
 * - `officeapp-dev-e2e-user` — SystemAdmin smoke bot creds (existing).
 * - `officeapp-dev-e2e-approvers` — JSON map of role slots to
 *   { user_pool_id, client_id, username, password, region }.
 *   Created via `terraform apply` on the S20 e2e-approvers module.
 *
 * If the approvers secret is missing (which is the case in local dev
 * without staging AWS creds), every non-`system` role falls back to
 * the SystemAdmin smoke bot and logs a warning. The Playwright specs
 * that assert "server denies wrong-role decision" (T27) then fail —
 * which is the correct outcome, because we cannot verify role
 * partitioning without a partitioned pool.
 */
import { execFileSync } from "node:child_process";
import type { Page } from "@playwright/test";

import { mintStagingTokens as mintSystemTokens } from "./staging-auth";

export type RoleSlot =
  | "system"
  | "submitter"
  | "delivery"
  | "hr"
  | "finance"
  | "legal"
  | "ceo";

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

interface CachedTokens {
  fetchedAt: number;
  expiresAt: number;
  idToken: string;
  accessToken: string;
}

const cache = new Map<RoleSlot, CachedTokens>();
let approversMap: Record<RoleSlot, StagingCreds> | null = null;

function awsCli(args: string[]): string {
  return execFileSync("aws", args, {
    stdio: ["ignore", "pipe", "pipe"],
    env: process.env,
  })
    .toString()
    .trim();
}

/**
 * Load the multi-role Cognito credentials from Secrets Manager, or
 * return `null` if the secret does not exist. Callers fall back to the
 * SystemAdmin smoke bot in that case (see the block comment above).
 */
function loadApproversMap(): Record<RoleSlot, StagingCreds> | null {
  if (approversMap) return approversMap;
  const profile = process.env.AWS_PROFILE_STAGING ?? "lm-arbiter-poc";
  const secretId =
    process.env.STAGING_E2E_APPROVERS_SECRET ?? "officeapp-dev-e2e-approvers";
  const region = process.env.STAGING_E2E_REGION ?? "us-east-2";
  try {
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
    approversMap = JSON.parse(raw) as Record<RoleSlot, StagingCreds>;
    return approversMap;
  } catch {
    // Secret missing (local dev, or module not yet applied) → return null;
    // the caller falls back to the SystemAdmin smoke bot.
    approversMap = null;
    return null;
  }
}

function mintRoleTokensDirect(creds: StagingCreds): CachedTokens {
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
  const now = Date.now();
  return {
    fetchedAt: now,
    expiresAt: now + auth.ExpiresIn * 1000,
    idToken: auth.IdToken,
    accessToken: auth.AccessToken,
  };
}

/**
 * Mint (or return cached) tokens for a role slot.
 *
 * Cached within the process until 60s before expiry so a slow suite
 * doesn't hammer Cognito.
 */
export function mintRoleTokens(role: RoleSlot): {
  idToken: string;
  accessToken: string;
  expiresAt: number;
} {
  const now = Date.now();
  const cached = cache.get(role);
  if (cached && cached.expiresAt - 60_000 > now) {
    return {
      idToken: cached.idToken,
      accessToken: cached.accessToken,
      expiresAt: cached.expiresAt,
    };
  }
  // The `system` slot always uses the existing smoke-bot secret.
  if (role === "system") {
    const sys = mintSystemTokens();
    const entry: CachedTokens = {
      fetchedAt: now,
      expiresAt: sys.expiresAt,
      idToken: sys.idToken,
      accessToken: sys.accessToken,
    };
    cache.set(role, entry);
    return { idToken: entry.idToken, accessToken: entry.accessToken, expiresAt: entry.expiresAt };
  }
  const map = loadApproversMap();
  const creds = map?.[role];
  if (!creds) {
    // Fall back to system slot when the partitioned secret is absent.
    // Spec that asserts role partitioning (T27) will fail loudly —
    // that is the intended signal that the pool needs partitioning.
    console.warn(
      `[multi-role-auth] role="${role}" has no creds in officeapp-dev-e2e-approvers; falling back to SystemAdmin smoke bot`,
    );
    return mintRoleTokens("system");
  }
  const entry = mintRoleTokensDirect(creds);
  cache.set(role, entry);
  return { idToken: entry.idToken, accessToken: entry.accessToken, expiresAt: entry.expiresAt };
}

/**
 * Attach the role's Cognito tokens to `page` before it navigates.
 *
 * Uses `addInitScript` (same pattern as `staging-auth.ts`) so tokens
 * land in sessionStorage before app JS runs. Call this before
 * `page.goto()`; subsequent `actAs()` calls swap tokens live via
 * `page.evaluate` and can be paired with `page.reload()` to force the
 * app to re-read its identity.
 */
export async function authAsRole(page: Page, role: RoleSlot): Promise<void> {
  const { idToken, accessToken, expiresAt } = mintRoleTokens(role);
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

/**
 * Swap the page's identity to a different role at runtime. Playwright
 * evaluates the storage write in the page context; the caller decides
 * whether to `page.reload()` after (usually yes, so the SPA rebuilds
 * its permission-aware surface).
 */
export async function actAs(page: Page, role: RoleSlot): Promise<void> {
  const { idToken, accessToken, expiresAt } = mintRoleTokens(role);
  await page.evaluate(
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

/**
 * Return an Authorization header value for direct API calls (e.g.
 * fetch inside a spec to seed data before UI actions). Callers should
 * pair this with the tag prefixes from `isolation.md` §7 so the
 * scheduled cleanup can reap the row on the next tick.
 */
export function bearerFor(role: RoleSlot): { Authorization: string } {
  const { accessToken } = mintRoleTokens(role);
  return { Authorization: `Bearer ${accessToken}` };
}
