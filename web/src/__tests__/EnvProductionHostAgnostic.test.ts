/**
 * The production bundle is served from more than one hostname.
 *
 * `d1mu2un4hj9akj.cloudfront.net` and `dealgate.smartek21.com` are the same
 * distribution, and any absolute hostname baked into `.env.production` is
 * correct on exactly one of them. When the domain was added, this file pinned
 * the API base to the CloudFront host, which would have made every API call on
 * the custom domain cross-origin — and the API has no CORS middleware, so they
 * would have failed outright rather than degraded.
 *
 * The failure mode is quiet: the page loads, the shell renders, and only the
 * data is missing. These assertions make it loud instead.
 */

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// Resolved from cwd, not import.meta.url: under jsdom `import.meta.url` is an
// http:// URL and fileURLToPath rejects it. Vitest sets cwd to the directory
// holding vite.config.ts, which is web/ both locally and in CI.
const ENV_PATH = resolve(process.cwd(), ".env.production");

function entries(): Map<string, string> {
  if (!existsSync(ENV_PATH)) {
    throw new Error(
      `.env.production not found at ${ENV_PATH} — this guard is silently ` +
        `passing on nothing. Check the cwd assumption above.`,
    );
  }
  const out = new Map<string, string>();
  for (const raw of readFileSync(ENV_PATH, "utf8").split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    out.set(line.slice(0, eq).trim(), line.slice(eq + 1).trim());
  }
  return out;
}

describe(".env.production", () => {
  it("points the API at a same-origin relative path, not a hostname", () => {
    expect(entries().get("VITE_API_BASE_URL")).toBe("/api");
  });

  it("pins no OAuth redirect, so login returns to whichever host was loaded", () => {
    const env = entries();
    // Absent, not blank. The fallback in auth/cognito.ts is a `??`, and "" is
    // not nullish — a blank value yields a blank redirect_uri, which Cognito
    // rejects at the authorize call.
    expect(env.has("VITE_COGNITO_REDIRECT_URI")).toBe(false);
    expect(env.has("VITE_COGNITO_LOGOUT_URI")).toBe(false);
  });

  it("names no deployment hostname in any value", () => {
    const offenders = [...entries()].filter(([, v]) =>
      /cloudfront\.net|smartek21\.com/.test(v),
    );
    // The Cognito hosted UI is an amazoncognito.com endpoint and is genuinely
    // absolute — it is not a host the SPA is served from, so it is exempt.
    expect(offenders).toEqual([]);
  });
});
