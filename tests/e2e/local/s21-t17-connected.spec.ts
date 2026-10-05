import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test.use({ baseURL: process.env.S21_T17_WEB_URL ?? "http://127.0.0.1:5211" });
const continuation = process.env.S21_T17_CONTINUE === "confirmed-scope";

test(continuation ? "T17 diagnostic continuation from persisted confirmed scope" : "T17 connected empty deal through actual execution and handoff", async ({ page, request }) => {
  test.setTimeout(600_000);
  page.setDefaultTimeout(20_000);
  const f = JSON.parse(readFileSync(process.env.S21_T17_RECEIPT ?? "/tmp/s21-t17-61d71c0b.json", "utf8"));
  const run = f.run.replaceAll("-", "");
  expect(f.database).toBe(`s21_t17_${run}`);
  expect(run).toMatch(/^[0-9a-f]{32}$/);
  const sourcePath = `/tmp/s21-t17-${run.slice(0, 8)}-sow.docx`;
  const sourceHash = createHash("sha256").update(readFileSync(sourcePath)).digest("hex");
  const api = process.env.S21_T17_API_URL ?? "http://127.0.0.1:8211";
  expect(["http://127.0.0.1:8211", "http://127.0.0.1:8212"]).toContain(api);
  const deal = f.fixture.opportunity_id;
  const client = f.fixture.client_id;
  const clientName = `S21 e2e ${f.fixture.run_id} T17 connected ${run.slice(0, 8)}`;
  let actor = f.people.owner.email;
  const proof: unknown[] = [];
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), "X-Test-User": actor } }));
  function record(condition: string, value: unknown) {
    proof.push({ condition, value, at: new Date().toISOString() });
    writeFileSync(`../../docs/s21/evidence/baseline/t17-${run.slice(0, 8)}-${continuation ? "continuation" : "connected-browser"}.json`, JSON.stringify({
      revision: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
      database: f.database, boundary: f.boundary, proof,
    }, null, 2));
  }
  async function get(path: string) {
    const response = await request.get(`${api}${path}`, { headers: { "X-Test-User": actor } });
    expect(response.status(), path).toBe(200);
    return response.json();
  }
  let version: { id: string; file_hash: string; extract_status: string; confirmed_at: string | null };
  if (!continuation) {
  const zero = execFileSync("docker", ["exec", "dealgate-s21-lead-db", "psql", "-U", "s21", "-d", f.database,
    "-At", "-c", "SELECT json_build_object('sows',(SELECT count(*) FROM sow),'versions',(SELECT count(*) FROM sow_version),'packages',(SELECT count(*) FROM approval_package),'projects',(SELECT count(*) FROM project))"], { encoding: "utf8" });
  expect(JSON.parse(zero)).toEqual({ sows: 0, versions: 0, packages: 0, projects: 0 });
  await page.goto("/pipeline");
  await page.getByText(clientName, { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/clients/${client}$`));
  await page.getByTestId(`client-deal-row-${deal}`).click();
  await expect(page).toHaveURL(new RegExp(`/deals/${deal}$`));
  await expect(page.getByRole("button", { name: "Delete SOW", exact: true })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Readiness", exact: true })).toHaveCount(0);
  await expect(page.getByText("No SOW", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t17-empty-deal.png", fullPage: true });
  record("T17.01/.04 empty named deal", JSON.parse(zero));
  await page.getByRole("button", { name: "Upload SOW", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`bindOppId=${deal}`));
  await page.getByTestId("upload-file-input").setInputFiles(sourcePath);
  await page.getByTestId("upload-submit").click();
  await expect(page).toHaveURL(new RegExp(`/sows/${deal}/staffing$`), { timeout: 240_000 });
  version = await get(`/sow/opportunity/${deal}/current`);
  expect(version.file_hash).toBe(sourceHash);
  expect(version.extract_status).toBe("complete");
  record("real extraction/source binding", { id: version.id, hash: version.file_hash });
  await page.getByRole("button", { name: "Complete scope", exact: true }).click();
  await expect(page.getByTestId("confirmation-submit")).toBeEnabled();
  await page.getByTestId("confirmation-submit").click();
  await expect(page).toHaveURL(new RegExp(`/sows/${deal}/approvals$`));
  await page.getByRole("tab", { name: "Staffing & GM", exact: true }).click();
  } else {
    version = await get(`/sow/opportunity/${deal}/current`);
    expect(version.id).toBe("d95a10b3-9811-418a-b6ef-958d148c00b7");
    expect(version.confirmed_at).not.toBeNull();
    expect((await get(`/deals/${deal}`)).latest_package).toBeNull();
    await page.goto(`/sows/${deal}/staffing`);
    record("diagnostic continuation, not continuous T17 proof", { version: version.id });
  }
  if (await page.getByRole("button", { name: "Commercial pricing", exact: true }).count()) {
    await page.getByRole("button", { name: "Commercial pricing", exact: true }).click();
  }
  const model = page.getByRole("region", { name: "Commercial model", exact: true });
  await expect(model).toBeVisible();
  for (const [label, value] of Object.entries({ Workstream: "assessment", "Service start": "2026-10-01",
    "Service end": "2026-10-31", Timezone: "America/New_York", Currency: "USD", "Billing cadence": "upon_delivery",
    "Cost basis": "Fixed subcontracted assessment fee including all labor", "Total fee": "24000",
    "Allocation basis": "Explicit single-month US allocation in signed test source", "Currency minor unit": "0.01" })) {
    await model.getByLabel(label, { exact: true }).fill(value);
  }
  await model.getByLabel("Source evidence", { exact: true }).fill(`SOW ${version.id}: synthetic fixed fee, US October allocation and loaded subcontract cost clauses; SHA256 ${version.file_hash}`);
  if (!continuation) await model.getByRole("button", { name: "Add allocation", exact: true }).click();
  await expect(model.getByLabel("Allocation month 1", { exact: true })).toHaveCount(1);
  await model.getByLabel("Allocation month 1", { exact: true }).fill("2026-10-01");
  await model.getByLabel("Allocation location 1", { exact: true }).selectOption("US");
  await model.getByLabel("Allocation weight 1", { exact: true }).fill("1");
  if (!continuation) await model.getByRole("button", { name: "Add period cost", exact: true }).click();
  await expect(model.getByLabel("Cost month 1", { exact: true })).toHaveCount(1);
  await model.getByLabel("Cost month 1", { exact: true }).fill("2026-10-01");
  await model.getByLabel("Cost location 1", { exact: true }).selectOption("US");
  await model.getByLabel("Loaded cost 1", { exact: true }).fill("10000");
  await model.getByLabel("All delivery costs confirmed", { exact: true }).check();
  await model.getByLabel("Change reason", { exact: true }).fill("Confirm explicit synthetic fixed assessment terms");
  const saved = page.waitForResponse(response => response.request().method() === "POST" && response.url().includes("/commercial/versions"));
  await model.getByRole("button", { name: "Save version", exact: true }).click();
  const savedResponse = await saved;
  expect(savedResponse.status()).toBe(201);
  const savedModel = (await savedResponse.json()).gm_model;
  expect(savedModel.computed.complete).toBe(true);
  expect(savedModel.commercial_snapshot.schedule.rows).toHaveLength(1);
  expect(savedModel.commercial_snapshot.schedule.rows[0]).toMatchObject({
    month: "2026-10-01", location: "US",
  });
  expect(Number(savedModel.commercial_snapshot.schedule.rows[0].revenue)).toBe(24000);
  expect(Number(savedModel.commercial_snapshot.schedule.rows[0].cost)).toBe(10000);
  record("independent fixed assessment economics", savedModel.commercial_snapshot.schedule);
  await page.reload();
  await expect(page.getByText("Financials complete", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Approvals", exact: true }).click();
  const reviewers = page.getByRole("region", { name: "Planned reviewers", exact: true });
  for (const [role, label] of [["delivery", "Delivery"], ["hr", "HR"], ["sales", "Sales"], ["finance", "Finance"], ["legal", "Legal"]]) {
    await reviewers.getByLabel(`${label} approver`, { exact: true }).selectOption(f.people[role].id);
  }
  await reviewers.getByRole("button", { name: "Confirm submission", exact: true }).click();
  await expect(page.getByTestId("review-delivery")).toBeVisible();
  record("scope/financials/review submission", { sow_version: version.id });
  for (const [role, label] of [["delivery", "Delivery"], ["hr", "HR"], ["sales", "Sales"], ["finance", "Finance"], ["legal", "Legal"]]) {
    actor = f.people[role].email;
    await page.reload();
    const review = page.getByTestId(`review-${role}`);
    await review.getByLabel(`${label} reason`, { exact: true }).fill(`T17 ${label} confirms the actual synthetic source and frozen economics`);
    await review.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(page.getByRole("heading", { name: `${label} · Approved`, exact: true })).toBeVisible();
    record("distinct reviewer approved", { role, person: f.people[role].id });
  }
  actor = f.people.owner.email;
  await page.reload();
  await page.getByRole("tab", { name: "Signature", exact: true }).click();
  await page.getByLabel("Executed document", { exact: true }).setInputFiles(sourcePath);
  await page.getByLabel("This document contains signature evidence", { exact: true }).check();
  await page.getByRole("button", { name: "Upload executed document", exact: true }).click();
  await expect(page.getByText("Verification: pending", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Verify executed document", exact: true }).click();
  await expect(page.getByText("Verification: verified", { exact: true })).toBeVisible({ timeout: 180_000 });
  record("actual signed bytes verified", { sow_version: version.id });
  actor = f.people.delivery.email;
  await page.reload();
  await page.getByRole("tab", { name: "Handoff", exact: true }).click();
  for (const label of ["Staffing confirmed", "Billing setup confirmed", "PO confirmed"]) await page.getByLabel(label, { exact: true }).check();
  await page.getByLabel("Acceptance notes", { exact: true }).fill("Synthetic fixed assessment delivery setup confirmed by assigned Delivery reviewer");
  await page.getByRole("button", { name: "Record delivery acceptance", exact: true }).click();
  await expect(page.getByRole("region", { name: "Handoff status", exact: true })).toContainText("Delivery acceptance: Recorded");
  actor = f.people.owner.email;
  await page.reload();
  await page.getByRole("button", { name: "Release handoff", exact: true }).click();
  await expect(page.getByText("Handoff release: Released", { exact: true })).toBeVisible({ timeout: 60_000 });
  await page.reload();
  await expect(page.getByText("Handoff release: Released", { exact: true })).toBeVisible();
  const persisted = JSON.parse(execFileSync("docker", ["exec", "dealgate-s21-lead-db", "psql", "-U", "s21", "-d", f.database,
    "-At", "-c", "SELECT json_build_object('agreements',(SELECT count(*) FROM agreement),'projects',(SELECT json_agg(json_build_object('id',id,'opportunity_id',opportunity_id,'sow_version_id',sow_version_id,'gm_model_id',gm_model_id,'package_id',package_id)) FROM project),'approvals',(SELECT json_agg(json_build_object('function',function,'approver_id',approver_id,'decision',decision)) FROM approval))"], { encoding: "utf8" }));
  expect(persisted.agreements).toBe(0);
  expect(persisted.projects).toHaveLength(1);
  expect(persisted.projects[0]).toMatchObject({ opportunity_id: deal, sow_version_id: version.id, gm_model_id: savedModel.id });
  expect(persisted.approvals).toHaveLength(5);
  for (const role of ["delivery", "hr", "sales", "finance", "legal"]) {
    expect(persisted.approvals.find((a: { function: string }) => a.function === role)).toEqual({
      function: role, approver_id: f.people[role].id, decision: "approve",
    });
  }
  record("persisted five reviewers and single source-bound project, no agreements", persisted);
  expect(errors).toEqual([]);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t17-released.png", fullPage: true });
  record(continuation ? "diagnostic confirmed-scope to handoff, not full T17.02" : "T17.02 continuous browser core", { released: true, errors });
});
