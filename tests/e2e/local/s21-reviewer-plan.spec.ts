import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test("T05 direct Approvals preview validates reviewers and freezes selected assignments", async ({ page, request }, testInfo) => {
  test.setTimeout(120_000);
  const manifest = process.env.S21_REVIEW_MANIFEST;
  if (!manifest) throw new Error("S21_REVIEW_MANIFEST must identify a fresh isolated fixture");
  const f = JSON.parse(readFileSync(manifest, "utf8"));
  expect(f.database).toMatch(/^s21_review_[0-9a-f]{32}$/);
  const sql = (query: string) => JSON.parse(execFileSync("docker", ["exec", "dealgate-s21-lead-db", "psql", "-U", "s21", "-d", f.database, "-At", "-v", "ON_ERROR_STOP=1", "-c", query], { encoding: "utf8", timeout: 20_000 }).trim());
  const counts = () => sql("SELECT json_build_object('packages',(SELECT count(*) FROM approval_package),'assignments',(SELECT count(*) FROM approval_assignment),'tasks',(SELECT count(*) FROM task))");
  expect(counts()).toEqual({ packages: 0, assignments: 0, tasks: 0 });
  const api = "http://127.0.0.1:8210";
  const headers = { "X-Test-User": f.actor_email };
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  // Go directly to Approvals without any earlier reviewer-selection interaction.
  await page.goto(f.approvals_path);
  const editor = page.getByRole("region", { name: "Planned reviewers", exact: true });
  await expect(editor).toBeVisible();
  await expect(editor).toContainText("Frozen package: SOW v1");
  await expect(editor).toContainText("GM v1");
  const response = await request.get(`${api}/approvals/plan/${f.deal_id}`, { headers });
  expect(response.status()).toBe(200);
  const plan = await response.json();
  expect(plan.sow_version_id).toBe(f.sow_version_id);
  expect(plan.gm_model_id).toBe(f.gm_model_id);
  expect(plan.executive).toBeNull();
  expect(plan.rows.map((r: any) => r.function).sort()).toEqual(["delivery", "finance", "hr", "legal", "sales"]);
  for (const row of plan.rows) {
    const roster = f.roster[row.function];
    expect(row.approver_id).toBe(roster.default_id);
    expect(row.members.map((m: any) => m.id).sort()).toEqual([...roster.eligible_ids].sort());
    const select = editor.getByRole("combobox", { name: `${row.label} approver`, exact: true });
    await expect(select).toHaveValue(roster.default_id);
    for (const member of row.members) {
      const actor: any = Object.values(f.actors).find((a: any) => a.id === member.id);
      expect(member.name).toBe(actor.name);
      await expect(select.locator(`option[value="${member.id}"]`)).toHaveText(actor.name);
    }
  }
  const body = { sow_version_id: f.sow_version_id, gm_model_id: f.gm_model_id,
    assignments: Object.fromEntries(plan.rows.map((r: any) => [r.function, { approver_id: r.approver_id, due_date: r.due_date, use_sla: r.use_sla }])) };
  for (const id of [f.invalid_reviewer_id, f.unauthorized_id, f.actor_id]) {
    const invalid = structuredClone(body);
    invalid.assignments.delivery.approver_id = id;
    const refused = await request.post(`${api}/approvals/packages/${f.deal_id}`, { headers, data: invalid });
    expect(refused.status(), await refused.text()).toBe(422);
    expect(counts()).toEqual({ packages: 0, assignments: 0, tasks: 0 });
  }
  const duplicate = structuredClone(body);
  duplicate.assignments.delivery.approver_id = f.delivery_alternative_id;
  duplicate.assignments.hr.approver_id = f.delivery_alternative_id;
  const duplicateResponse = await request.post(`${api}/approvals/packages/${f.deal_id}`, { headers, data: duplicate });
  expect(duplicateResponse.status(), await duplicateResponse.text()).toBe(422);
  expect(counts()).toEqual({ packages: 0, assignments: 0, tasks: 0 });
  const unauthorized = await request.post(`${api}/approvals/packages/${f.deal_id}`, { headers: { "X-Test-User": f.unauthorized_email }, data: body });
  expect(unauthorized.status(), await unauthorized.text()).toBe(403);
  expect(counts()).toEqual({ packages: 0, assignments: 0, tasks: 0 });
  await editor.getByRole("combobox", { name: "Delivery approver", exact: true }).selectOption(f.delivery_alternative_id);
  const submitted = page.waitForResponse(r => r.url().endsWith(`/approvals/packages/${f.deal_id}`) && r.request().method() === "POST");
  await editor.getByRole("button", { name: "Confirm submission", exact: true }).click();
  const saved = await submitted;
  expect(saved.status(), await saved.text()).toBe(201);
  await expect(editor).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId("review-delivery").getByRole("heading", { name: "Delivery · Pending with T05 Delivery Alternate", exact: true })).toBeVisible();
  await expect(editor).toHaveCount(0);
  expect(counts()).toEqual({ packages: 1, assignments: 5, tasks: 3 });
  const stored = sql("SELECT json_build_object('packages',(SELECT json_agg(json_build_object('sow_version_id',sow_version_id,'gm_model_id',gm_model_id,'status',status)) FROM approval_package),'assignments',(SELECT json_object_agg(function,approver_id) FROM approval_assignment),'owners',(SELECT json_agg(owner_id ORDER BY owner_id) FROM task),'active_tasks',(SELECT count(*) FROM task WHERE status='assigned'))");
  expect(stored.packages).toEqual([{ sow_version_id: f.sow_version_id, gm_model_id: f.gm_model_id, status: f.expected.after_submit.status }]);
  expect(stored.assignments).toEqual(f.expected.after_submit.assignments);
  expect(stored.owners.sort()).toEqual([...f.expected.after_submit.task_owners].sort());
  expect(stored.active_tasks).toBe(3);
  await testInfo.attach("stored-reviewer-proof", { body: JSON.stringify(stored, null, 2), contentType: "application/json" });
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t05-reviewer-plan.png", fullPage: true });
});
