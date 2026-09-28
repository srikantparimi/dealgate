/**
 * S18 §1 · run-tag teardown helper.
 *
 * Every e2e spec that creates staging data must tag its clients with a
 * run-tag string containing the spec's short prefix (``s17-e2e-``,
 * ``s18-e2e-``, ``smoke-e2e-``, ...) plus a timestamp. This helper wraps
 * a Playwright test with an ``afterAll`` that ALWAYS runs — pass, fail,
 * timeout — and hard-deletes every client on staging whose name
 * contains the run tag.
 *
 * Use exactly this pattern in every spec that hits ``/api``:
 *
 *   import { registerRunTag } from "../fixtures/tag-teardown";
 *   const RUN_TAG = `s18-e2e-${Date.now()}`;
 *   registerRunTag(RUN_TAG);
 *
 * Do NOT rely on an in-test `await api.delete(...)` at the end of the
 * body — those don't run when an assertion above throws.
 */
import { test, request as pwRequest } from "@playwright/test";
import { mintStagingTokens } from "./staging-auth";

const BASE_URL = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";

export function registerRunTag(tag: string): void {
  test.afterAll(async () => {
    if (!tag) return;
    const { accessToken } = mintStagingTokens();
    const api = await pwRequest.newContext({
      baseURL: `${BASE_URL}/api/`,
      extraHTTPHeaders: { Authorization: `Bearer ${accessToken}` },
      timeout: 60_000,
    });
    try {
      const res = await api.get("clients?size=200");
      if (!res.ok()) return;
      const body = (await res.json()) as { items?: Array<{ id: string; name: string }> };
      const targets = (body.items ?? []).filter((c) =>
        (c.name ?? "").includes(tag),
      );
      for (const c of targets) {
        try {
          await api.delete(`clients/${c.id}?reason=tag-teardown`);
        } catch {
          // best-effort — nightly worker will sweep whatever survives
        }
      }
      if (targets.length > 0) {
        // eslint-disable-next-line no-console
        console.log(`[tag-teardown] deleted ${targets.length} clients for tag ${tag}`);
      }
    } finally {
      await api.dispose();
    }
  });
}
