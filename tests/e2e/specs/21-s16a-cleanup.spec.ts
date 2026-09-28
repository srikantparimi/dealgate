import { expect, test } from "@playwright/test";

test("S16a local tracking, retired routes and released projects", async ({ page, request }, testInfo) => {
  test.setTimeout(120_000);
  test.skip(process.env.S16_LOCAL_PROOF !== "1", "Requires disposable s16a_local.py fixture");
  const api = "http://127.0.0.1:8026";
  const headers = { "X-Test-User": "s16-owner@example.test" };
  await page.setExtraHTTPHeaders(headers);
  // UI identity only. The local fixture authenticates the header, not this token.
  await page.addInitScript(() => {
    const claims = { sub: "s16-local", email: "s16-owner@example.test", name: "Morgan Example", "cognito:groups": ["SystemAdmin", "Legal", "Sales"] };
    sessionStorage.setItem("dealgate.cognito.id_token", `fixture.${btoa(JSON.stringify(claims))}.fixture`);
    sessionStorage.setItem("dealgate.cognito.expires_at", String(Date.now() + 3600000));
  });
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto("/agreements");
  await expect(page.getByRole("table", { name: "Agreement register" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Projects", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Margin lab|Legacy|Delivery & actuals/ })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("agreements-before.png"), fullPage: true });
  const tasks = await (await request.get(`${api}/tasks`, { headers })).json();
  expect(tasks.items.filter((t: { subject: string }) => /Obtain NDA|Obtain MSA/.test(t.subject))).toHaveLength(2);
  expect(tasks.items.filter((t: { category: string }) => t.category === "coverage").every((t: { record_url: string }) => t.record_url.startsWith("/agreements?entity="))).toBe(true);
  await page.goto("/work");
  await expect(page.getByText("Obtain NDA - Example Systems", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("agreement-tasks.png"), fullPage: true });
  await page.goto("/agreements");
  const file = await (await request.get(`${api}/__s16/fixture.docx`)).body();
  for (const kind of ["NDA", "MSA"]) {
    await page.getByRole("button", { name: `Upload signed ${kind}`, exact: true }).click();
    await page.getByLabel("Signed PDF or DOCX").setInputFiles({ name: "signed.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: file });
    await expect(page.getByLabel("Effective date")).toBeVisible();
    await page.getByLabel("Effective date").fill("2026-01-01");
    await page.getByLabel("Expiry date").fill("2027-12-31");
    await page.getByLabel("Reason for date correction").fill("Verified dates against the signed fixture document");
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "File as executed" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  await expect(page.getByText("Executed", { exact: true })).toHaveCount(2);
  await page.screenshot({ path: testInfo.outputPath("agreements-executed.png"), fullPage: true });
  const completed = await (await request.get(`${api}/tasks`, { headers })).json();
  expect(completed.items.filter((t: { subject: string; status: string }) => /Obtain NDA|Obtain MSA/.test(t.subject)).every((t: { status: string }) => t.status === "done")).toBe(true);
  for (const path of ["/tasks", "/deals", "/deals/legacy-id", "/gm/sandbox", "/margin-lab"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: "This page has moved" })).toBeVisible();
    await expect(page.getByText("404", { exact: true })).toBeVisible();
  }
  await page.screenshot({ path: testInfo.outputPath("retired-route.png"), fullPage: true });
  await page.goto("/projects");
  await expect(page.getByRole("link", { name: "Reporting platform delivery" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Reporting platform delivery resources" })).toContainText("Alice");
  await expect(page.getByRole("table", { name: "Reporting platform delivery GM" })).toContainText("50.0%");
  await expect(page.getByRole("table", { name: "Reporting platform delivery GM" })).toContainText("95.0%");
  await page.screenshot({ path: testInfo.outputPath("projects-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("link", { name: "Reporting platform delivery" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("projects-mobile.png"), fullPage: true });
  await page.goto("/agreements");
  await expect(page.getByRole("table", { name: "Agreement register" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("agreements-mobile.png"), fullPage: true });
  expect(errors).toEqual([]);
});
