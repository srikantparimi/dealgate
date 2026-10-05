import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:5211" });

test("T17 repair verifies existing signed bytes then accepts and releases exactly once", async ({ page, request }) => {
  test.setTimeout(240_000);
  const f = JSON.parse(readFileSync("/tmp/s21-t17-61d71c0b.json", "utf8"));
  expect(f.database).toBe("s21_t17_61d71c0b4bf7436d957723c632fe1aba");
  const pkg = "7a2404c1-b3ae-4bc6-850b-7cf6f436a7c8";
  const gm = "6eae85bf-cc2d-4233-af18-9d4298bceaed";
  const deal = f.fixture.opportunity_id;
  let actor = f.people.owner.email;
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), "X-Test-User": actor } }));
  const headers = { "X-Test-User": actor };
  const read = await request.get(`http://127.0.0.1:8211/signed-sow/${pkg}`, { headers });
  expect(read.status()).toBe(200);
  expect(await read.json()).toMatchObject({ id: "49f4ab59-a384-4f76-96e3-e623830f5221",
    verify_status: "blocked", verify_reason: "price_mismatch", released_at: null,
    file_hash: "7104c0fe8432aac30032689e0e8d89d6fe752bff0001b730826f08083561c0fc" });
  await page.goto(`/sows/${deal}/signature`);
  const verified = page.waitForResponse(response => response.request().method() === "POST" && response.url().endsWith(`/signed-sow/${pkg}/verify`), { timeout: 180_000 });
  await page.getByRole("button", { name: "Verify executed document", exact: true }).click();
  const result = await verified;
  expect(result.status()).toBe(200);
  const upload = await result.json();
  expect(upload.verify_status).toBe("verified");
  expect(upload.diff_json.match).toBe(true);
  expect(upload.diff_json.fields.find((field: { field: string }) => field.field === "price")).toMatchObject({
    approved: "USD 24000.00", match: true,
    approved_currency: "USD", extracted_currency: "USD",
  });
  await expect(page.getByText("Verification: verified", { exact: true })).toBeVisible();
  actor = f.people.delivery.email;
  await page.reload();
  await page.getByRole("tab", { name: "Handoff", exact: true }).click();
  for (const label of ["Staffing confirmed", "Billing setup confirmed", "PO confirmed"]) await page.getByLabel(label, { exact: true }).check();
  await page.getByLabel("Acceptance notes", { exact: true }).fill("Synthetic fixed subcontracted assessment delivery setup confirmed");
  await page.getByRole("button", { name: "Record delivery acceptance", exact: true }).click();
  await expect(page.getByRole("region", { name: "Handoff status", exact: true })).toContainText("Delivery acceptance: Recorded");
  actor = f.people.owner.email;
  await page.reload();
  await page.getByRole("button", { name: "Release handoff", exact: true }).click();
  await expect(page.getByText("Handoff release: Released", { exact: true })).toBeVisible({ timeout: 60_000 });
  function persisted() {
    return JSON.parse(execFileSync("docker", ["exec", "dealgate-s21-lead-db", "psql", "-U", "s21", "-d", f.database,
      "-At", "-c", "SELECT json_build_object('agreements',(SELECT count(*) FROM agreement),'projects',(SELECT json_agg(json_build_object('id',id,'opportunity_id',opportunity_id,'sow_version_id',sow_version_id,'gm_model_id',gm_model_id,'package_id',package_id,'baseline',baseline_snapshot_json)) FROM project),'tasks',(SELECT count(*) FROM task),'uploads',(SELECT count(*) FROM signed_sow_upload))"], { encoding: "utf8" }));
  }
  const before = persisted();
  expect(before.agreements).toBe(0);
  expect(before.uploads).toBe(1);
  expect(before.projects).toHaveLength(1);
  expect(before.projects[0]).toMatchObject({ opportunity_id: deal, gm_model_id: gm, package_id: pkg,
    sow_version_id: "d95a10b3-9811-418a-b6ef-958d148c00b7" });
  const replay = await request.post(`http://127.0.0.1:8211/signed-sow/${pkg}/release`, { headers });
  expect(replay.status()).toBe(409);
  expect((await replay.json()).detail.error).toBe("release_gate_not_met");
  expect(persisted()).toEqual(before);
  await page.reload();
  await expect(page.getByText("Handoff release: Released", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t17-repaired-handoff.png", fullPage: true });
  writeFileSync("../../docs/s21/evidence/baseline/t17-repaired-handoff.json", JSON.stringify({
    revision: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    database: f.database, verification: upload, persistence: before, repeat_release: 409,
    boundary: "Diagnostic continuation, not uninterrupted T17.02; real S3/Bedrock, local identities and SES sink",
  }, null, 2));
});
