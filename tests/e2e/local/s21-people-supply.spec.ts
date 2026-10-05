import { expect, test } from "@playwright/test";

test("managed workforce upload persists exact dated supply and immutable correction history", async ({ page, request }) => {
  test.setTimeout(60_000);
  const source = `synthetic-browser-${crypto.randomUUID()}`;
  const person = { person_key: "synthetic-engineer", display_name: "Synthetic engineer",
    role: "Engineer", skills: ["python"], level: "senior", location: "US", timezone: "America/Los_Angeles",
    evidence: ["Synthetic roster row one"], intervals: [{ kind: "gross", allocation: "0.123456789012345678901",
      start_date: "2026-11-01", end_date: "2026-11-30", assignment_key: null }] };
  const roster = { source_system: source, source_as_of: "2026-10-01T12:00:00Z",
    basis: "gross_with_commitments", people: [person] };
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/people");
  await expect(page.getByRole("heading", { name: "People planning", exact: true })).toBeVisible();
  const form = page.getByRole("form", { name: "Managed roster import" });
  await form.getByLabel("Roster file").setInputFiles({ name: "synthetic-roster.json", mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(roster)) });
  await expect(form.getByLabel("Roster JSON", { exact: true })).toHaveValue(JSON.stringify(roster));
  await form.getByLabel("Import reason").fill("Connected synthetic workforce import proof");
  await form.getByRole("button", { name: "Import roster" }).click();
  await expect(page.getByRole("status")).toContainText("Imported revision 1: 1 people.");
  const supply = page.getByRole("region", { name: "Workforce supply" });
  const row = supply.getByRole("row").filter({ hasText: source });
  await expect(row).toContainText("0.123456789012345678901");
  await expect(row).toContainText("2026-11-01 to 2026-11-30");
  await page.reload();
  await expect(row).toContainText("Synthetic engineer");
  const correction = { ...roster, source_as_of: "2026-10-02T00:00:00Z", people: [{ ...person, display_name: "Corrected synthetic engineer" }] };
  await form.getByLabel("Roster file").setInputFiles({ name: "synthetic-correction.json", mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(correction)) });
  await form.getByLabel("Import reason").fill("Correct managed display name while preserving exact capacity");
  await form.getByRole("button", { name: "Import roster" }).click();
  await expect(page.getByRole("status")).toContainText("Imported revision 2: 1 people.");
  await expect(row).toContainText("Corrected synthetic engineer");
  const history = page.getByRole("region", { name: "Import history" });
  await expect(history.getByRole("row").filter({ hasText: source })).toHaveCount(2);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/people-supply-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/people-supply-mobile.png", fullPage: true });
  const response = await request.get("http://127.0.0.1:8210/people/availability", { headers: { "X-Test-User": "s21-browser@example.test" } });
  expect(response.ok()).toBe(true);
  const persisted = (await response.json()).people.filter((item: { source_system: string }) => item.source_system === source);
  expect(persisted).toHaveLength(1);
  expect(persisted[0].person_key).toBe("synthetic-engineer");
  expect(persisted[0].intervals[0].allocation).toBe("0.123456789012345678901");
  expect(errors).toEqual([]);
});
