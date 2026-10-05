/**
 * S21F:T15.01 — upload a real fixture file through the UI for every
 * pricing profile, on staging, with real Bedrock extraction.
 *
 * One isolated trusted fixture per profile; the upload binds to it via
 * `/sows/new?bindOppId=…&bindClientId=…` so no business data is touched
 * and no picker fires. Each client is deleted afterward and its durable
 * deletion job polled to `done`. Owner approved the bounded Bedrock
 * cost for this run (release push, 2026-10-04).
 */
import {
  test,
  expect,
  request as pwRequest,
  type APIRequestContext,
} from "@playwright/test";
import * as path from "node:path";
import { authStaging, mintStagingTokens } from "../../fixtures/staging-auth";

const BASE_URL = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..", "..");
const FIXTURES = path.join(REPO_ROOT, "fixtures", "sample_sows");

const PROFILES: Array<{ file: string; engagement: string }> = [
  { file: "01_staff_aug_us.pdf", engagement: "staff_aug" },
  { file: "02_managed_service_india.pdf", engagement: "managed_service" },
  { file: "03_fixed_price_mixed.pdf", engagement: "fixed_price" },
  { file: "04_assessment_4week.pdf", engagement: "assessment" },
  { file: "05_tm_capped.pdf", engagement: "tm|time_and_materials" },
  { file: "06_below_floor.pdf", engagement: "fixed_price" },
  { file: "08_assessment_fixed_fee.docx", engagement: "assessment|fixed_price" },
];

async function apiCtx(): Promise<APIRequestContext> {
  const { accessToken } = mintStagingTokens();
  return pwRequest.newContext({
    baseURL: `${BASE_URL}/api/`,
    extraHTTPHeaders: { Authorization: `Bearer ${accessToken}` },
  });
}

async function issueFixture(api: APIRequestContext, label: string) {
  const me = await (await api.get("me")).json();
  const res = await api.post("dev/test-fixtures", {
    data: { label, reviewer_ids: [me.id], hours: 1 },
  });
  expect(res.status(), await res.text()).toBe(201);
  return res.json();
}

async function deleteAndDrain(api: APIRequestContext, clientId: string) {
  const res = await api.delete(`clients/${clientId}`, {
    params: { reason: "T15 seven-profile teardown" },
  });
  expect(res.status(), await res.text()).toBe(202);
  const { job_id } = await res.json();
  for (let i = 0; i < 75; i++) {
    const state = await (await api.get(`deletion-jobs/${job_id}`)).json();
    if (state.status === "done") return;
    await new Promise((r) => setTimeout(r, 4000));
  }
  throw new Error(`deletion job ${job_id} did not drain`);
}

test.describe("T15.01 · seven pricing profiles through the UI", () => {
  test.setTimeout(420_000);

  for (const profile of PROFILES) {
    test(`uploads ${profile.file} and extracts the ${profile.engagement} profile`, async ({
      page,
    }) => {
      const api = await apiCtx();
      const label = `S21 e2e t15 ${profile.engagement} ${Date.now()}`;
      const fixture = await issueFixture(api, label);
      try {
        await authStaging(page, BASE_URL);
        await page.goto(
          `${BASE_URL}/sows/new?bindOppId=${fixture.opportunity_id}&bindClientId=${fixture.client_id}`,
        );
        await page
          .getByTestId("upload-file-input")
          .setInputFiles(path.join(FIXTURES, profile.file));
        await expect(page.getByTestId("upload-file-staged")).toBeVisible();
        await page.getByTestId("upload-submit").click();

        // Real Bedrock extraction: a pre-bound upload lands on the SOW
        // workspace once the pipeline completes. Never accept an error.
        await page.waitForURL(/\/sows\//, { timeout: 300_000 });
        expect(await page.getByTestId("upload-error").count()).toBe(0);
        await expect(page.getByRole("tab", { name: "Staffing & GM" })).toBeVisible();

        // The deployed pipeline bound the upload to the issued fixture
        // and the extraction completed with the expected profile.
        const versions = await (
          await api.get(`sows/${fixture.opportunity_id}/versions`)
        ).json();
        const rows = versions.versions ?? [];
        expect(rows.length).toBeGreaterThanOrEqual(1);
        expect(rows[0].extract_status).toBe("complete");
        const detail = await (
          await api.get(`sow/versions/${rows[0].id}`)
        ).json();
        const suggested = detail.extracted_fields?.engagement_type_suggested?.value;
        expect(
          profile.engagement.split("|"),
          `got ${suggested} for ${profile.file}`,
        ).toContain(suggested);
      } finally {
        await deleteAndDrain(api, fixture.client_id);
        await api.dispose();
      }
    });
  }
});
