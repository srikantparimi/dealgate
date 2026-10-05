import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:5212" });

test("T17 released readiness names responsibility and assigned roles can read Documents", async ({ page, request }) => {
  const receipt = JSON.parse(readFileSync("/tmp/s21-t17-8d7c388a.json", "utf8"));
  const deal = receipt.fixture.opportunity_id as string;
  const database = receipt.database as string;
  let actor = receipt.people.owner.email as string;
  const errors: string[] = [];
  const evidence: unknown[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/**", route => {
    expect(route.request().method()).toBe("GET");
    return route.continue({ headers: { ...route.request().headers(), "X-Test-User": actor } });
  });
  const counts = () => execFileSync("docker", ["exec", "dealgate-s21-lead-db", "psql", "-X", "-qAt",
    "-U", "s21", "-d", database, "-c", `SELECT json_build_object('sows',(SELECT count(*) FROM sow WHERE opportunity_id='${deal}'),'projects',(SELECT count(*) FROM project WHERE opportunity_id='${deal}'),'packages',(SELECT count(*) FROM approval_package WHERE opportunity_id='${deal}'))`],
  { encoding: "utf8" }).trim();
  const before = counts();
  await page.goto(`/sows/${deal}/handoff`);
  const readiness = page.getByRole("region", { name: "Readiness", exact: true });
  await expect(readiness).toContainText("Delivery acceptance");
  await expect(readiness).toContainText("Recorded");
  await expect(readiness).toContainText("Handoff released");
  await expect(readiness).toContainText("Released");
  await expect(readiness).toContainText(`Owner: ${receipt.people.owner.name}`);
  await expect(page.getByRole("button", { name: "View handoff", exact: true })).toBeVisible();
  evidence.push({ role: "owner", route: `/sows/${deal}/handoff`, readiness: "recorded/released/named owner" });

  for (const role of ["legal", "hr"] as const) {
    actor = receipt.people[role].email;
    const response = await request.get(`http://127.0.0.1:8212/sows/${deal}/versions`, {
      headers: { "X-Test-User": actor },
    });
    expect(response.status(), role).toBe(200);
    await page.goto(`/sows/${deal}/documents`);
    await expect(page.getByTestId("sow-version-history")).toBeVisible();
    await expect(page.getByTestId("version-row-1")).toBeVisible();
    await expect(page.getByTestId("version-error")).toHaveCount(0);
    evidence.push({ role, route: `/sows/${deal}/documents`, history_status: 200 });
  }
  expect(errors).toEqual([]);
  expect(counts()).toBe(before);
  writeFileSync("../../docs/s21/evidence/baseline/t17-readiness-routes.json", JSON.stringify({
    revision: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    boundary: "Read-only local identity adapter and actual API/PG/UI; not Cognito or staging",
    database, evidence, errors,
  }, null, 2));
});
