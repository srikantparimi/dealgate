/**
 * S22 P5c-4 · the import refuses rather than guessing, on the deployed SPA.
 *
 *   /import/forecast-model → upload the synthetic fixture (it carries "Zeta Unlisted": no dashboard row and one
 *   person with no Location) → the dry run shows the panel "Fix these in the workbook before loading" with both
 *   blockers and the Load button disabled → a dry_run=false call made directly against the API returns 422 with
 *   {blockers} and creates nothing (the engagement count seen by this identity is unchanged).
 *
 * The dry run writes nothing, so no fixture account is needed; the direct load is refused before any write.
 */
import { expect, request as pwRequest, test, type APIRequestContext } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { authAsRole, bearerFor } from "../../fixtures/multi-role-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
const LOCAL_USER = process.env.E2E_LOCAL_USER;
const API_BASE = process.env.E2E_API_BASE ? `${process.env.E2E_API_BASE}/` : `${BASE}/api/`;
const authHeaders = (): Record<string, string> => (LOCAL_USER ? { "X-Test-User": LOCAL_USER } : bearerFor("system"));
const REPO = path.resolve(__dirname, "..", "..", "..", "..");
const MODEL = path.join(REPO, "api/tests/forecast/fixtures/forecast_model_synthetic.xlsx"); // the full fixture, blockers included

let api: APIRequestContext;

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

test.beforeAll(async () => {
  api = await pwRequest.newContext({ baseURL: API_BASE, extraHTTPHeaders: authHeaders(), timeout: 120_000 });
});
test.afterAll(async () => {
  await api.dispose();
});

test("S22 P5c-4 · the dry run lists both blockers for Zeta Unlisted and Load is disabled", async ({ page }) => {
  if (!LOCAL_USER) await authAsRole(page, "system");
  await page.goto(`${BASE}/import/forecast-model`);
  await expect(page.getByRole("heading", { name: "Import the forecast model" })).toBeVisible();
  await page.getByLabel("Forecast model (.xlsx)").setInputFiles(MODEL);
  const panel = page.getByTestId("blockers-panel");
  await expect(panel).toBeVisible({ timeout: 120_000 });
  await expect(panel).toContainText("Fix these in the workbook before loading");
  const blockers = panel.getByTestId("blocker");
  await expect(blockers).toHaveCount(2);
  const kinds = await blockers.evaluateAll((els) => els.map((e) => `${e.getAttribute("data-kind")}:${e.getAttribute("data-tab")}`).sort());
  expect(kinds).toEqual(["business_unit:Zeta Unlisted", "location:Zeta Unlisted"]);
  await expect(panel.getByTestId("blocker-fix").first()).toContainText("Dashboard (RunRate)");
  await expect(panel.getByTestId("blocker-fix").last()).toContainText("Fill the Location column");
  await expect(page.getByTestId("load-button")).toBeDisabled();
  await expect(page.getByTestId("blockers-count")).toContainText("2 things to fix · re-upload when the workbook carries them");
  // the dry-run report itself leads with the blockers, above the as-of line
  await expect(page.getByTestId("dry-run-report")).toContainText("Zeta Unlisted");
});

test("S22 P5c-4 · a load called directly is 422 {blockers} and creates nothing", async () => {
  const before = ((await (await api.get("engagements?page_size=1")).json()) as { total: number }).total;
  const response = await api.post("engagements/import-forecast-model", {
    multipart: {
      file: { name: "model.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: fs.readFileSync(MODEL) },
      dry_run: "false",
      as_of: "2026-02",
    },
  });
  expect(response.status()).toBe(422);
  const body = (await response.json()) as { detail: { blockers?: { kind: string; tab: string; fix: string }[]; errors?: string[] } };
  expect(body.detail.errors).toBeUndefined();
  expect((body.detail.blockers ?? []).map((b) => `${b.kind}:${b.tab}`).sort()).toEqual(["business_unit:Zeta Unlisted", "location:Zeta Unlisted"]);
  const after = ((await (await api.get("engagements?page_size=1")).json()) as { total: number }).total;
  expect(after).toBe(before);
});
