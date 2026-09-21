/**
 * S13a — delete-and-reset + archive-refuses-delete, browser proof.
 *
 * DoD #1 (portal delete with cascade confirmation), #2 (fresh re-upload),
 * #3 (same-file second upload → duplicate flag), #4 (approved record
 * refuses delete + offers archive), #6 (e2e leaves zero residue).
 *
 * Screenshots land in `docs/reports/s13a/` (checked in).
 *
 * The suite tags every fixture client with a `S13a e2e <timestamp>`
 * prefix so `afterAll` can delete any residue via the DELETE endpoint,
 * satisfying DoD #6.
 */
import {
  test,
  expect,
  request as pwRequest,
  type Page,
} from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  authStaging,
  cleanupClientsByPrefix,
  mintStagingTokens,
} from "../fixtures/staging-auth";

const BASE_URL =
  process.env.E2E_BASE_URL ?? "https://d1mu2un4hj9akj.cloudfront.net";
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const SCREENSHOT_DIR = path.join(REPO_ROOT, "docs", "reports", "s13a");
const FIXTURE_PDF = path.join(
  REPO_ROOT,
  "fixtures",
  "sample_sows",
  "03_fixed_price_mixed.pdf",
);
// Different bytes so the approve flow doesn't collide with the reupload's
// hash (which is what test 3 + 4 have already put in the DB).
const APPROVE_FIXTURE_PDF = path.join(
  REPO_ROOT,
  "fixtures",
  "sample_sows",
  "05_tm_capped.pdf",
);

const RUN_TAG = `S13a e2e ${Date.now()}`;

async function shot(page: Page, name: string) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${name}.png`),
    fullPage: true,
  });
}

async function apiCtx() {
  const { accessToken } = mintStagingTokens();
  // Trailing slash + relative paths — `new URL('/foo', 'https://host/api')`
  // drops the `/api` because leading-slash paths reset the URL's path.
  return pwRequest.newContext({
    baseURL: `${BASE_URL}/api/`,
    extraHTTPHeaders: { Authorization: `Bearer ${accessToken}` },
  });
}

test.describe.serial("S13a portal delete + archive proof", () => {
  test.setTimeout(300_000);

  let opportunityId: string | undefined;
  let clientId: string | undefined;

  test.beforeAll(async () => {
    // The fixture PDF resolves to "Peppermill Casino". Any leftover from a
    // previous run auto-matches and skips the picker, which breaks our tag
    // strategy. Nuke it up front so the picker fires and we can rename.
    await cleanupClientsByPrefix(BASE_URL, "Peppermill");
    await cleanupClientsByPrefix(BASE_URL, "S13a e2e");
  });

  test("upload a fresh SOW, tag the client with the run marker", async ({ page }) => {
    await authStaging(page, BASE_URL);
    await page.goto(`${BASE_URL}/sows/new`);
    await expect(page.getByTestId("upload-file-input")).toBeVisible();
    await page.getByTestId("upload-file-input").setInputFiles(FIXTURE_PDF);
    await page.getByTestId("upload-submit").click();

    await Promise.race([
      page.waitForURL(/opportunityId=|\/sows\/[0-9a-f-]{36}\/staffing/, {
        timeout: 240_000,
      }),
      page.waitForSelector('[data-testid="picker-create-new"]', {
        timeout: 240_000,
      }),
    ]);
    if (
      await page.getByTestId("picker-create-new").isVisible().catch(() => false)
    ) {
      await page.getByTestId("picker-create-new").click();
      const legalName = page.getByTestId("picker-new-legal-name");
      // Overwrite whatever the extractor filled in — we want the S13a tag
      // so `afterAll` can find the row.
      await legalName.fill(`${RUN_TAG} · Fresh Upload`);
      await page.getByTestId("picker-submit").click();
      await page.waitForURL(
        /opportunityId=|\/sows\/[0-9a-f-]{36}\/staffing/,
        { timeout: 240_000 },
      );
    }

    const url = page.url();
    const oppMatch = /[?&]opportunityId=([0-9a-f-]+)/i.exec(url);
    const stfMatch = /\/sows\/([0-9a-f-]{36})\/staffing/.exec(url);
    opportunityId = (oppMatch && oppMatch[1]) || (stfMatch && stfMatch[1]) || undefined;
    expect(opportunityId).toBeTruthy();

    // Resolve client id via the confirmation payload.
    const api = await apiCtx();
    const confirmResp = await api.get(`sow/${opportunityId}/confirmation`);
    const conf = await confirmResp.json();
    clientId =
      conf.source?.client?.id ??
      conf.source?.client_id ??
      undefined;
    expect(clientId).toBeTruthy();

    await page.goto(`${BASE_URL}/pipeline`);
    await expect(page.getByText(RUN_TAG)).toBeVisible({ timeout: 30_000 });
    await shot(page, "01-fresh-client-on-pipeline");
  });

  test("row-menu → Delete → cascade counts → confirm → list empty", async ({
    page,
  }) => {
    expect(clientId).toBeTruthy();
    await authStaging(page, BASE_URL);
    await page.goto(`${BASE_URL}/pipeline`);
    // Find the row and open its kebab menu.
    const rowMenu = page.getByTestId(`row-menu-${clientId}`);
    await expect(rowMenu).toBeVisible({ timeout: 30_000 });
    await rowMenu.click();
    await page.getByTestId(`row-delete-${clientId}`).click();

    // The confirmation dialog opens with the assessment counts.
    const dialog = page.getByTestId("deletion-dialog");
    await expect(dialog).toBeVisible({ timeout: 30_000 });
    // Counts render — proof that we called /deletion-assessment.
    await expect(dialog).toContainText(/opportunit/i);
    await shot(page, "02-cascade-confirmation-modal");
    await dialog.getByTestId("deletion-confirm").click();

    // On success the dialog closes and the row is gone.
    await expect(dialog).not.toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(RUN_TAG)).toHaveCount(0, { timeout: 30_000 });
    await shot(page, "03-list-empty-after-delete");
  });

  test("re-upload same file cleanly (no duplicate flag)", async ({ page }) => {
    await authStaging(page, BASE_URL);
    const api = await apiCtx();
    const buf = fs.readFileSync(FIXTURE_PDF);
    const res = await api.post("sows/upload", {
      multipart: {
        file: {
          name: "s13a-reupload.pdf",
          mimeType: "application/pdf",
          buffer: buf,
        },
      },
    });
    const body = await res.json();
    expect(body.duplicate ?? false).toBe(false);
    expect(["needs_pick", "done"]).toContain(body.status);
    if (body.status === "needs_pick") {
      await api.post(`sows/jobs/${body.job_id}/pick`, {
        data: {
          create_new: {
            legal_name: `${RUN_TAG} · Reupload`,
            domain: null,
            address_lines: [],
          },
        },
      });
    }
    await page.goto(`${BASE_URL}/pipeline`);
    await expect(page.getByText(`${RUN_TAG} · Reupload`)).toBeVisible({
      timeout: 30_000,
    });
    await shot(page, "04-reupload-clean");
  });

  test("second upload of same bytes → duplicate=true", async () => {
    const api = await apiCtx();
    const buf = fs.readFileSync(FIXTURE_PDF);
    const res = await api.post("sows/upload", {
      multipart: {
        file: {
          name: "s13a-second.pdf",
          mimeType: "application/pdf",
          buffer: buf,
        },
      },
    });
    const body = await res.json();
    expect(body.duplicate).toBe(true);
  });

  test("seeded-approved record: row-menu Delete refused, Archive offered, delete API returns 409, archive keeps history", async ({
    page,
  }) => {
    await authStaging(page, BASE_URL);
    const api = await apiCtx();

    // Fresh bytes — different from the reupload hash.
    const buf = fs.readFileSync(APPROVE_FIXTURE_PDF);
    const boundary = Date.now().toString();
    const res = await api.post("sows/upload", {
      multipart: {
        file: {
          name: `s13a-approve-${boundary}.pdf`,
          mimeType: "application/pdf",
          buffer: buf,
        },
      },
    });
    const upBody = await res.json();
    if (upBody.status === "needs_pick") {
      await api.post(`sows/jobs/${upBody.job_id}/pick`, {
        data: {
          create_new: {
            legal_name: `${RUN_TAG} · Approve`,
            domain: null,
            address_lines: [],
          },
        },
      });
    }
    let approveOppId: string | undefined;
    for (let i = 0; i < 60 && !approveOppId; i++) {
      const j = await api.get(`sows/jobs/${upBody.job_id}`);
      const jb = await j.json();
      if (jb.status === "done") approveOppId = jb.opportunity_id;
      if (jb.status === "failed") throw new Error(`job failed: ${jb.error}`);
      await new Promise((r) => setTimeout(r, 2000));
    }
    expect(approveOppId).toBeTruthy();

    // Navigate to a real origin before any `page.evaluate` — sessionStorage
    // is not readable from `about:blank`.
    await page.goto(`${BASE_URL}/pipeline`);

    // Seed the approved-package state via the browser context — CloudFront
    // routes `/api/*` verb+deep-path requests fine for the SPA fetch but not
    // for the raw Node http agent (see docs/reports/s13a.md §follow-ups),
    // and the browser fetch is the code path the app actually uses.
    const seedResult = await page.evaluate(async (oppId) => {
      const t = sessionStorage.getItem("dealgate.cognito.access_token");
      const resp = await fetch(`/api/dev/seed-approved-package/${oppId}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${t ?? ""}`,
        },
        body: "{}",
      });
      return { status: resp.status, body: await resp.text() };
    }, approveOppId);
    // CloudFront's CustomErrorResponses map 4xx from origin to /index.html
    // + 200, so a bare status check would silently accept an ALB 4xx.
    // The seed endpoint always returns 200 with `{ok, ...}`.
    expect(
      seedResult.status,
      `seed body=${seedResult.body.slice(0, 300)}`,
    ).toBe(200);
    expect(
      seedResult.body.startsWith("{"),
      `seed returned HTML — body=${seedResult.body.slice(0, 200)}`,
    ).toBe(true);
    const seedJson = JSON.parse(seedResult.body);
    expect(
      seedJson.ok,
      `seed reported failure: ${JSON.stringify(seedJson)}`,
    ).toBe(true);
    expect(seedJson.package_id).toBeTruthy();

    // Sanity: the deletion-assessment on the client now says approved.
    const clientResp = await api.get(`sow/${approveOppId}/confirmation`);
    const cb = await clientResp.json();
    const approvedClientId =
      cb.source?.client?.id ?? cb.source?.client_id ?? undefined;
    expect(approvedClientId).toBeTruthy();

    // Delete via API must be refused with 409 (assess_client → approved →
    // deletion.delete_client raises DeletionError 409). Use the browser
    // fetch so CloudFront routing is identical to the UI's own call path.
    const deleteResult = await page.evaluate(async (id) => {
      const t = sessionStorage.getItem("dealgate.cognito.access_token");
      const resp = await fetch(
        `/api/clients/${id}?reason=e2e%20should-refuse`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${t ?? ""}` },
        },
      );
      return { status: resp.status, body: await resp.text() };
    }, approvedClientId);
    expect(deleteResult.status, `delete body=${deleteResult.body}`).toBe(409);

    // UI: the row-menu Delete… opens the dialog with the Archive-instead
    // button and no Delete button (canHardDelete === false).
    await page.goto(`${BASE_URL}/pipeline`);
    await page.getByTestId(`row-menu-${approvedClientId}`).click();
    await page.getByTestId(`row-delete-${approvedClientId}`).click();
    const dialog = page.getByTestId("deletion-dialog");
    await expect(dialog).toBeVisible({ timeout: 30_000 });
    await expect(dialog.getByTestId("deletion-archive")).toBeVisible({
      timeout: 30_000,
    });
    await expect(dialog.getByTestId("deletion-confirm")).toHaveCount(0);
    await shot(page, "05-approved-refuses-delete");

    // Click Archive → dialog closes, row disappears from the default view,
    // and the approval-package history row is still there (soft archive).
    await dialog.getByTestId("deletion-archive").click();
    await expect(dialog).not.toBeVisible({ timeout: 30_000 });
    await page.goto(`${BASE_URL}/pipeline`);
    await expect(page.getByText(`${RUN_TAG} · Approve`)).toHaveCount(0);
    await shot(page, "06-archived-row-hidden-from-defaults");

    // History-kept assertion: the approval package still resolves — the
    // archive is a soft-hide on the client row, not a cascade delete.
    const pkgs = await page.evaluate(async (oppId) => {
      const t = sessionStorage.getItem("dealgate.cognito.access_token");
      const r = await fetch(
        `/api/approvals/packages?opportunity_id=${oppId}&size=5`,
        { headers: { Authorization: `Bearer ${t ?? ""}` } },
      );
      return { status: r.status, body: await r.text() };
    }, approveOppId);
    expect(pkgs.status).toBe(200);
    const pkgBody = JSON.parse(pkgs.body);
    expect(pkgBody.total ?? pkgBody.items?.length ?? 0).toBeGreaterThan(0);
  });
});

test.afterAll(async () => {
  const { deleted, skipped } = await cleanupClientsByPrefix(BASE_URL, RUN_TAG);
  // eslint-disable-next-line no-console
  console.log(`S13a cleanup: deleted=${deleted} skipped=${skipped}`);
});
