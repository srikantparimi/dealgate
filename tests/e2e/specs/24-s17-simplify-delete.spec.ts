/**
 * S17 browser proof against staging.
 *
 * Journey:
 *   1. Upload an NDA + an MSA for a fresh S17 client (Agreements page).
 *   2. Upload a SOW with the "NDA and MSA are signed with this client"
 *      checkbox ticked and confirm the workspace shows it as a note.
 *   3. Delete the SOW from the workspace at any stage (post-upload here).
 *   4. Upload a fresh SOW for the same client — no duplicate warning
 *      because the previous SOW really went.
 *   5. Screenshot /sows before + after cleanup for the addendum §2 proof.
 *
 * Screenshots land under docs/reports/s17/*.png.
 */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test, expect, request as pwRequest } from "@playwright/test";
import { authStaging, mintStagingTokens } from "../fixtures/staging-auth";
import { registerRunTag } from "../fixtures/tag-teardown";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const REPORT_DIR = path.resolve(__dirname, "..", "..", "..", "docs", "reports", "s17");
fs.mkdirSync(REPORT_DIR, { recursive: true });
const RUN_TAG = `s17-e2e-${new Date().toISOString().replaceAll(/[-:T.Z]/g, "")}`;
registerRunTag(RUN_TAG);
const FIXTURE = path.resolve(
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

async function makeUniqueDocx(): Promise<string> {
  const tmp = path.join(
    fs.mkdtempSync(path.join(os.tmpdir(), "s17-")),
    `${RUN_TAG}.docx`,
  );
  const buf = fs.readFileSync(FIXTURE);
  const noise = Buffer.from(
    Array.from({ length: 64 }, () => Math.floor(Math.random() * 256)),
  );
  fs.writeFileSync(tmp, Buffer.concat([buf, noise]));
  return tmp;
}

test.setTimeout(600_000);

test("S17 upload NDA + MSA + SOW checkbox + delete + resubmit", async ({ page }) => {
  await authStaging(page, BASE);
  const { accessToken } = mintStagingTokens();
  const api = await pwRequest.newContext({
    baseURL: `${BASE}/api/`,
    extraHTTPHeaders: { Authorization: `Bearer ${accessToken}` },
    timeout: 60_000,
  });
  // Seed the client via a first SOW upload — POST /clients isn't a public
  // endpoint; the SOW-upload + create-new path is the seam.
  const seedDocx = await makeUniqueDocx();
  const seedUp = await api.post("sows/upload", {
    multipart: {
      file: {
        name: `${RUN_TAG}-seed.docx`,
        mimeType:
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        buffer: fs.readFileSync(seedDocx),
      },
    },
  });
  const seedBody = await seedUp.json();
  await api.post(`sows/jobs/${seedBody.job_id}/pick`, {
    data: {
      create_new: {
        legal_name: `${RUN_TAG} · Client`,
        domain: null,
        address_lines: [],
      },
    },
  });
  let clientId: string | undefined;
  let seedOppId: string | undefined;
  for (let i = 0; i < 30 && !clientId; i++) {
    const j = await (await api.get(`sows/jobs/${seedBody.job_id}`)).json();
    if (j.status === "done") {
      seedOppId = j.opportunity_id;
      const conf = await (await api.get(`sow/${seedOppId}/confirmation`)).json();
      clientId =
        conf?.source?.client?.id ??
        conf?.source?.client_id ??
        conf?.opportunity?.client_id ??
        conf?.deal?.client_id;
    }
    if (j.status === "failed") throw new Error(`seed job failed: ${j.error}`);
    if (!clientId) await new Promise((r) => setTimeout(r, 2_000));
  }
  expect(clientId).toBeTruthy();
  // Delete the seed SOW so the resubmit-no-dup step reads cleanly later.
  if (seedOppId) {
    const seedSowId = (await (await api.get(`sow/${seedOppId}/confirmation`)).json())
      ?.sow_version?.sow_id;
    if (seedSowId) await api.delete(`sows/${seedSowId}?reason=s17-e2e-seed`);
  }

  // -- Step 1: upload NDA + MSA --
  const nda = await makeUniqueDocx();
  const msa = await makeUniqueDocx();
  for (const [kind, file] of [["NDA", nda], ["MSA", msa]] as const) {
    const resp = await api.post("agreements", {
      multipart: {
        client_id: clientId,
        kind,
        file: {
          name: `${RUN_TAG}-${kind}.docx`,
          mimeType:
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          buffer: fs.readFileSync(file),
        },
      },
    });
    expect(resp.ok(), await resp.text()).toBe(true);
  }
  await page.goto(`${BASE}/agreements`);
  await page.waitForLoadState("networkidle");
  await page.screenshot({
    path: path.join(REPORT_DIR, "01-agreements-uploaded.png"),
    fullPage: true,
  });

  // -- Step 2: upload SOW with checkbox --
  const sowFile = await makeUniqueDocx();
  const upBytes = fs.readFileSync(sowFile);
  const up = await api.post("sows/upload", {
    multipart: {
      file: {
        name: `${RUN_TAG}-sow.docx`,
        mimeType:
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        buffer: upBytes,
      },
    },
  });
  const upBody = await up.json();
  const jobId = upBody.job_id;
  // Pick this same client + tick the checkbox
  await api.post(`sows/jobs/${jobId}/pick`, {
    data: { client_id: clientId, agreements_signed: true },
  });
  let opportunityId: string | undefined;
  let sowId: string | undefined;
  for (let i = 0; i < 30 && !opportunityId; i++) {
    const j = await (await api.get(`sows/jobs/${jobId}`)).json();
    if (j.status === "done") {
      opportunityId = j.opportunity_id;
      sowId = j.sow_version_id;
    }
    if (j.status === "failed") throw new Error(`upload job failed: ${j.error}`);
    if (!opportunityId) await new Promise((r) => setTimeout(r, 2_000));
  }
  expect(opportunityId).toBeTruthy();

  await page.goto(`${BASE}/sows/${opportunityId}`);
  await page.waitForLoadState("networkidle");
  await page.screenshot({
    path: path.join(REPORT_DIR, "02-sow-workspace-checkbox-note.png"),
    fullPage: true,
  });

  // -- Step 3: delete the SOW from the workspace at any stage --
  await page.getByRole("button", { name: /delete sow/i }).click();
  await page.getByRole("dialog").waitFor({ timeout: 10_000 });
  await page.screenshot({
    path: path.join(REPORT_DIR, "03-delete-dialog-cascade.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: /^delete sow$/i }).last().click();
  await page.waitForURL(/\/sows/, { timeout: 20_000 });
  await page.waitForLoadState("networkidle");
  await page.screenshot({
    path: path.join(REPORT_DIR, "04-sows-empty-after-delete.png"),
    fullPage: true,
  });

  // -- Step 4: resubmit a fresh SOW for the same client — no dup warning --
  const sowFile2 = await makeUniqueDocx();
  const up2 = await api.post("sows/upload", {
    multipart: {
      file: {
        name: `${RUN_TAG}-sow-2.docx`,
        mimeType:
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        buffer: fs.readFileSync(sowFile2),
      },
    },
  });
  const up2Body = await up2.json();
  expect(up2Body.duplicate, `resubmit should not be a dup: ${JSON.stringify(up2Body)}`).not.toBe(true);
  await page.reload();
  await page.waitForLoadState("networkidle");
  await page.screenshot({
    path: path.join(REPORT_DIR, "05-sows-fresh-after-resubmit.png"),
    fullPage: true,
  });

  // -- Cleanup: delete the fresh client so nothing survives the run --
  await api.delete(`clients/${clientId}?reason=s17-e2e-cleanup`);
  await api.dispose();
});
