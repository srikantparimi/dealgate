/**
 * S19 slice 1 · J6 — webhook-to-pipeline latency proof.
 *
 * Two modes, one spec:
 *
 * 1. **Observer** (default when `E2E_DEAL_NAME` is set) — the operator
 *    creates a HubSpot deal by hand with the given name, then this
 *    spec logs in, opens /pipeline, and polls until the deal appears
 *    (up to 2 minutes). No CRM writes from the harness. Used when the
 *    Playwright runner lacks HubSpot deal-create rights.
 *
 * 2. **Creator** (default when `E2E_DEAL_NAME` is unset) — the spec
 *    mints a HubSpot deal via CRM v3, waits for it to land, cleans up
 *    on teardown. Requires the staging HubSpot token to have `crm.
 *    objects.deals.write`.
 *
 * Both modes drop screenshots for J7 under `docs/reports/s19-1/`.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { execFileSync } from "node:child_process";
import { test, expect } from "@playwright/test";
import { authStaging } from "../fixtures/staging-auth";

const REPORTS = path.resolve(__dirname, "..", "..", "..", "docs", "reports");
const S19_DIR = path.join(REPORTS, "s19-1");
fs.mkdirSync(S19_DIR, { recursive: true });

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const HUBSPOT_TOKEN_SECRET_ID = "dealgate/staging/hubspot_token";
const AWS_PROFILE = process.env.AWS_PROFILE_STAGING ?? "lm-arbiter-poc";
const AWS_REGION = "us-east-2";
const HUBSPOT_API = "https://api.hubapi.com";

const OBSERVER_DEAL_NAME = process.env.E2E_DEAL_NAME?.trim() ?? "";
const OBSERVER_MODE = OBSERVER_DEAL_NAME.length > 0;
const AUTO_MARKER = `S19-1 e2e ${new Date()
  .toISOString()
  .replaceAll(/[-:T.Z]/g, "")}`;
const MARKER = OBSERVER_MODE ? OBSERVER_DEAL_NAME : AUTO_MARKER;

function loadHubSpotToken(): string {
  const raw = execFileSync(
    "aws",
    [
      "--profile",
      AWS_PROFILE,
      "--region",
      AWS_REGION,
      "secretsmanager",
      "get-secret-value",
      "--secret-id",
      HUBSPOT_TOKEN_SECRET_ID,
      "--query",
      "SecretString",
      "--output",
      "text",
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  ).toString().trim();
  try {
    const parsed = JSON.parse(raw);
    return parsed.token ?? parsed.HUBSPOT_TOKEN ?? raw;
  } catch {
    return raw;
  }
}

async function createTestDeal(token: string): Promise<{ dealId: string }> {
  const res = await fetch(`${HUBSPOT_API}/crm/v3/objects/deals`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      properties: {
        dealname: MARKER,
        pipeline: "710688094",
        dealstage: "1038193692", // 1-Initial Contact/Prospecting
        amount: "12345",
      },
    }),
  });
  if (!res.ok) {
    throw new Error(
      `HubSpot deal create failed: ${res.status} ${await res.text()}`,
    );
  }
  const body = (await res.json()) as { id: string };
  return { dealId: body.id };
}

async function deleteTestDeal(token: string, dealId: string): Promise<void> {
  await fetch(`${HUBSPOT_API}/crm/v3/objects/deals/${dealId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => {
    /* best-effort teardown */
  });
}

test.describe("S19 slice 1 — webhook-to-pipeline (J6)", () => {
  test.setTimeout(4 * 60 * 1000);

  let dealId: string | null = null;
  let token: string | null = null;

  test.beforeAll(() => {
    if (!OBSERVER_MODE) {
      token = loadHubSpotToken();
    }
  });

  test.afterEach(async () => {
    if (!OBSERVER_MODE && dealId && token) {
      await deleteTestDeal(token, dealId);
      dealId = null;
    }
  });

  test("HubSpot deal appears at /pipeline within 2 minutes", async ({
    page,
  }) => {
    // 1. Materialise the deal (creator) or trust the operator did (observer).
    if (!OBSERVER_MODE) {
      const created = await createTestDeal(token as string);
      dealId = created.dealId;
    }

    // 2. Log in and land on /pipeline.
    await authStaging(page, BASE);
    await page.goto(`${BASE}/pipeline`);
    await expect(
      page.getByRole("heading", { name: /^Pipeline$/ }),
    ).toBeVisible();

    // 3. Screenshot the clients view for J7.
    await page.getByRole("tab", { name: /^Clients/ }).click();
    await expect(page.getByTestId("clients-table")).toBeVisible();
    await page.screenshot({
      path: path.join(S19_DIR, "clients-view.png"),
      fullPage: true,
    });

    // 4. Screenshot the summary bar + stage strip + sync banner.
    await page.getByTestId("summary-bar").screenshot({
      path: path.join(S19_DIR, "summary-bar.png"),
    });
    await page.getByTestId("stage-strip").screenshot({
      path: path.join(S19_DIR, "stage-strip.png"),
    });
    await page.getByTestId("sync-banner").screenshot({
      path: path.join(S19_DIR, "sync-banner.png"),
    });

    // 5. Poll /pipeline/opportunities until the marker shows up (or 2 min).
    await page.getByRole("tab", { name: /^Opportunities/ }).click();
    await expect(page.getByTestId("opportunities-table")).toBeVisible();

    const deadline = Date.now() + 2 * 60 * 1000;
    let found = false;
    while (Date.now() < deadline && !found) {
      await page.reload();
      await expect(page.getByTestId("opportunities-table")).toBeVisible();
      const marker = page.getByText(MARKER, { exact: false });
      if ((await marker.count()) > 0) {
        found = true;
        break;
      }
      await page.waitForTimeout(10_000);
    }
    expect(found, `deal ${MARKER} did not appear at /pipeline within 2 min`)
      .toBe(true);

    // 6. Screenshot the opportunities view + the freshly-landed row.
    await page.screenshot({
      path: path.join(S19_DIR, "opportunities-view.png"),
      fullPage: true,
    });
    await page.getByText(MARKER, { exact: false }).first().screenshot({
      path: path.join(S19_DIR, "webhook-created-test-deal.png"),
    });
  });
});
