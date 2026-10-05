import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("T11 deal comments and actions persist, attribute CRM notes and reject stale changes", async ({ page, request }, testInfo) => {
  test.setTimeout(120_000);
  page.setDefaultTimeout(10_000);
  const root = resolve(process.cwd(), "../..");
  const api = "http://127.0.0.1:8210";
  const headers = { "X-Test-User": `s21-t11-${randomUUID()}@example.test` };
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const peerHeaders = { "X-Test-User": `s21-t11-peer-${randomUUID()}@example.test` };
  const peerRegistration = await request.post(`${api}/dev/test-fixtures`, { headers: peerHeaders, data: { label: "T11 unrelated peer fixture", reviewer_ids: [] } });
  expect(peerRegistration.status()).toBe(201);
  const peerResponse = await request.get(`${api}/me`, { headers: peerHeaders });
  expect(peerResponse.status()).toBe(200);
  const peer = await peerResponse.json();
  const issued = await request.post(`${api}/dev/test-fixtures`, { headers, data: { label: "T11 connected tracking", reviewer_ids: [peer.id] } });
  expect(issued.status()).toBe(201);
  const fixture = await issued.json();
  const note = JSON.parse(execFileSync(`${root}/api/.venv/bin/python`, ["scripts/s21_tracking_note_fixture.py"], {
    cwd: root, encoding: "utf8", timeout: 30_000, env: { ...process.env, PYTHONPATH: `${root}/api:${root}`,
      POSTGRES_URL: "postgresql+asyncpg://s21@127.0.0.1:55421/s21_journey", DEALGATE_ENV: "local",
      DEALGATE_TENANT_ID: "s21-lead", S21_TRACKING_DEAL: fixture.opportunity_id },
  }).trim().split("\n").at(-1)!);
  await page.goto(`/deals/${fixture.opportunity_id}`);
  const comments = page.getByRole("region", { name: "Comments", exact: true });
  const crm = comments.getByTestId(`comment-${note.note_id}`);
  await expect(crm.getByText("Synthetic CRM Author", { exact: true })).toBeVisible();
  await expect(crm.getByText("HubSpot note", { exact: true })).toBeVisible();
  await expect(crm.getByText("Synthetic CRM note <script>not executable</script>", { exact: true })).toBeVisible();
  await expect(crm.locator("script")).toHaveCount(0);
  await expect(crm.getByRole("button")).toHaveCount(0);
  const currentNotes = await request.get(`${api}/deals/${fixture.opportunity_id}/comments`, { headers });
  expect(currentNotes.status()).toBe(200);
  const crmRow = (await currentNotes.json()).items.find((row: any) => row.id === note.note_id);
  const refused = await request.patch(`${api}/deal-comments/${note.note_id}`, { headers, data: { expected_revision: crmRow.revision, body: "Forbidden rewrite" } });
  expect(refused.status()).toBe(409);
  await comments.getByRole("button", { name: "Add comment" }).click();
  await comments.getByLabel("Comment", { exact: true }).fill("Client confirmed original scope");
  await comments.getByRole("button", { name: "Save comment" }).click();
  await expect(comments.getByText("Client confirmed original scope", { exact: true })).toBeVisible();
  const internal = comments.locator("li").filter({ hasText: "Client confirmed original scope" });
  await internal.getByRole("button", { name: "Edit comment" }).click();
  await comments.getByLabel("Comment", { exact: true }).fill("Client confirmed revised scope");
  await comments.getByRole("button", { name: "Save comment" }).click();
  const revised = comments.locator("li").filter({ hasText: "Client confirmed revised scope" });
  await revised.getByRole("button", { name: "Pin comment" }).click();
  await expect(revised.getByText("Pinned", { exact: true })).toBeVisible();
  await expect(revised.getByText("Edited", { exact: true })).toBeVisible();
  const actions = page.getByRole("region", { name: "Next action", exact: true });
  await actions.getByRole("button", { name: "Add action" }).click();
  await actions.getByLabel("Action title").fill("Confirm original delivery");
  await actions.getByLabel("Due date").fill("2026-11-02");
  await actions.getByRole("button", { name: "Save action" }).click();
  const action = actions.locator("li").filter({ hasText: "Confirm original delivery" });
  await action.getByRole("button", { name: "Edit action" }).click();
  await actions.getByLabel("Action title").fill("Confirm revised delivery");
  await actions.getByLabel("Due date").fill("2026-11-03");
  await actions.getByRole("button", { name: "Save action" }).click();
  const editedAction = actions.locator("li").filter({ hasText: "Confirm revised delivery" });
  await editedAction.getByRole("button", { name: "Mark complete" }).click();
  await expect(editedAction.getByTestId("next-action-status-complete")).toBeVisible();
  await page.reload();
  await expect(revised.getByText("Pinned", { exact: true })).toBeVisible();
  await expect(editedAction.getByText("Due 2026-11-03", { exact: true })).toBeVisible();
  await expect(editedAction.getByTestId("next-action-status-complete")).toBeVisible();
  const activity = page.getByRole("region", { name: "Activity timeline", exact: true });
  await expect(activity.getByText("HubSpot note", { exact: true })).toBeVisible();
  await expect(activity).toContainText("Client confirmed revised scope");
  await expect(activity).toContainText("Confirm revised delivery");
  const activityResponse = await request.get(`${api}/deals/${fixture.opportunity_id}/timeline`, { headers });
  expect(activityResponse.status()).toBe(200);
  const activityRows = (await activityResponse.json()).items;
  expect(activityRows[0].source).toBe("next_action");
  expect(activityRows[0].kind).toBe("status_change");
  expect(activityRows[0].body).toContain("complete");
  expect(activityRows[0].actor_name).toBeTruthy();
  expect(activityRows.map((row: any) => Date.parse(row.ts))).toEqual(activityRows.map((row: any) => Date.parse(row.ts)).sort((a: number, b: number) => b - a));
  const response = await request.get(`${api}/deals/${fixture.opportunity_id}/comments`, { headers });
  const saved = (await response.json()).items.find((row: any) => row.source === "internal");
  expect(saved.pinned).toBe(true);
  expect(saved.author_name).toBeTruthy();
  await expect(revised.getByText(saved.author_name, { exact: true })).toBeVisible();
  // A second genuine request changes the row after this editor captured its revision.
  await revised.getByRole("button", { name: "Edit comment" }).click();
  await comments.getByLabel("Comment", { exact: true }).fill("Unsent stale draft");
  const concurrent = await request.patch(`${api}/deal-comments/${saved.id}`, { headers, data: { expected_revision: saved.revision, body: "Concurrent accepted wording" } });
  expect(concurrent.status()).toBe(200);
  await comments.getByRole("button", { name: "Save comment" }).click();
  await expect(page.getByRole("alert")).toContainText("This record changed");
  await expect(comments.getByLabel("Comment", { exact: true })).toHaveValue("Unsent stale draft");
  const after = await request.get(`${api}/deals/${fixture.opportunity_id}/comments`, { headers });
  expect((await after.json()).items.find((row: any) => row.id === saved.id).body).toBe("Concurrent accepted wording");
  await page.getByRole("button", { name: "Reload tracking" }).click();
  await expect(comments.getByText("Concurrent accepted wording", { exact: true })).toBeVisible();
  await expect(comments.getByLabel("Comment", { exact: true })).toHaveValue("Unsent stale draft");
  await comments.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t11-tracking.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const races = execFileSync(`${root}/api/.venv/bin/python`, ["scripts/s21_tracking_pg.py"], {
    cwd: root, encoding: "utf8", timeout: 45_000, env: { ...process.env, PYTHONPATH: `${root}/api:${root}`,
      POSTGRES_URL: "postgresql+asyncpg://s21@127.0.0.1:55421/s21_journey", DEALGATE_ENV: "local",
      DEALGATE_TENANT_ID: "s21-lead", S21_TRACKING_DEAL: fixture.opportunity_id, S21_TRACKING_PEER: peer.id },
  });
  const proof = JSON.parse(races.trim().split("\n").at(-1)!);
  expect(proof.proofs).toHaveLength(3);
  for (const race of proof.proofs.slice(0, 2)) expect(race.http_statuses).toEqual([200, 409]);
  expect(proof.proofs[2].role_checks).toContain("HR allowed cross-author edit");
  const proofPath = testInfo.outputPath("postgres-tracking-races.json");
  writeFileSync(proofPath, JSON.stringify(proof, null, 2));
  await testInfo.attach("postgres-tracking-races", { path: proofPath, contentType: "application/json" });
});
