import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test("T22 half-time demand retains distinct people, exact capacity and probability independence", async ({ page, request }, testInfo) => {
  test.setTimeout(180_000);
  const path = process.env.S21_PART_MANIFEST;
  if (!path) throw new Error("S21_PART_MANIFEST requires a fresh isolated fixture");
  const f = JSON.parse(readFileSync(path, "utf8"));
  expect(f.database).toMatch(/^s21_part_[0-9a-f]{32}$/);
  const api = "http://127.0.0.1:8210";
  const headers = { "X-Test-User": f.actor_email };
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const publication = await request.post(`${api}/people/demand/publications`, { headers, data: f.publication_body });
  expect(publication.status(), await publication.text()).toBe(201);
  const published = await publication.json();
  expect(published.missing).toEqual([]);
  await page.goto("/people");
  const form = page.getByRole("form", { name: "Managed roster import" });
  await form.getByLabel("Roster file").setInputFiles({ name: "synthetic-half-time.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(f.roster)) });
  await form.getByLabel("Import reason").fill("Independent half-time capacity proof");
  await form.getByRole("button", { name: "Import roster", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Imported revision 1: 6 people.");
  await page.reload();
  const availability = await request.get(`${api}/people/availability`, { headers });
  expect(availability.status()).toBe(200);
  const people = (await availability.json()).people;
  expect(people).toHaveLength(6);
  const personKeys = new Map(people.map((p: any) => [p.person_id, p.person_key]));
  async function allocation(probability: string) {
    const response = await request.get(`${api}/people/demand/allocation?account_id=${f.account_id}`, { headers });
    expect(response.status()).toBe(200);
    const result = await response.json();
    expect(result.complete).toBe(true);
    expect(result.pending_sources).toEqual([]);
    expect(result.is_reservation).toBe(false);
    expect(result.months).toHaveLength(6);
    for (const month of result.months) {
      expect(month.peak_headcount).toBe(7);
      expect(Number(month.peak_fte)).toBe(3.5);
      expect(Number(month.gap_fte)).toBe(1);
    }
    expect(result.intervals.length).toBeGreaterThan(0);
    expect(result.intervals[0].start).toBe("2026-11-01");
    expect(result.intervals.at(-1).end_exclusive).toBe("2027-05-01");
    for (const interval of result.intervals) {
      expect(interval.demands).toHaveLength(2);
      for (const [location, quantity, matched, keys] of [["US", 2, 0.5, f.expected.us_person_keys], ["India", 5, 2, f.expected.india_person_keys]] as const) {
        const row = interval.demands.find((d: any) => d.location === location);
        expect(row.plan_id).toBe(f.plan_id);
        expect(row.quantity).toBe(quantity);
        expect(Number(row.probability)).toBe(Number(probability));
        expect(Number(row.required_fte)).toBe(quantity * 0.5);
        expect(Number(row.matched_fte)).toBe(matched);
        expect(Number(row.gap_fte)).toBe(0.5);
        expect(row.matches.map((m: any) => personKeys.get(m.person_id)).sort()).toEqual([...keys].sort());
        expect(row.matches.every((m: any) => Number(m.allocation) === 0.5)).toBe(true);
      }
    }
    await testInfo.attach(`allocation-${probability}`, { body: JSON.stringify(result, null, 2), contentType: "application/json" });
  }
  await allocation("0.70");
  async function sourcing(revision: number) {
    await page.goto("/people/sourcing");
    await expect(page.getByRole("button", { name: "Add rule", exact: true })).toBeEnabled();
    if (revision === 1) {
      expect(await page.getByRole("button", { name: /^Remove rule \d+$/ }).count()).toBe(0);
      for (const [index, location, days] of [[1, "US", "45"], [2, "India", "30"]] as const) {
        await page.getByRole("button", { name: "Add rule", exact: true }).click();
        await page.getByLabel(`Skill ${index}`, { exact: true }).fill("python");
        await page.getByLabel(`Location ${index}`, { exact: true }).fill(location);
        await page.getByLabel(`Lead days ${index}`, { exact: true }).fill(days);
      }
      await page.getByLabel("Rule change reason", { exact: true }).fill("Synthetic regional rules for half-time proof");
      await page.getByRole("button", { name: "Save rules", exact: true }).click();
      await expect(page.getByText(/Rules revision \d+ saved/)).toBeVisible();
    }
    await page.getByLabel("Published source", { exact: true }).selectOption(f.plan_id);
    await page.getByLabel("Draft reason", { exact: true }).fill(`Half-time proof revision ${revision}`);
    await page.getByRole("button", { name: "Prepare sourcing draft", exact: true }).click();
    await expect(page.getByText(`Sourcing draft revision ${revision} prepared`, { exact: true })).toBeVisible();
    await page.reload();
    await page.getByLabel("Published source", { exact: true }).selectOption(f.plan_id);
    const draft = page.getByRole("article").filter({ hasText: `Half-time proof revision ${revision}` });
    await expect(draft).toContainText("Ready for review");
    for (const [zone, quantity, matched, date] of [["America/New_York", "2", "1", "2026-09-17"], ["Asia/Kolkata", "5", "4", "2026-10-02"]]) {
      const rows = draft.getByRole("row").filter({ hasText: zone });
      await expect(rows.first()).toBeVisible();
      for (const row of await rows.all()) {
        const cells = row.getByRole("cell");
        await expect(cells.nth(2)).toHaveText(quantity);
        await expect(cells.nth(5)).toHaveText(matched);
        await expect(cells.nth(6)).toHaveText("1");
        await expect(cells.nth(9)).toHaveText(/^0\.50*$/);
        await expect(cells.nth(10)).toHaveText(date);
      }
    }
  }
  await sourcing(1);
  await page.goto(`/forecast?view=opportunities&account_id=${f.account_id}&as_of=2026-10-01T12:00:00Z`);
  await page.getByRole("button", { name: "Edit assumptions", exact: true }).click();
  const editor = page.getByRole("form", { name: "Edit planning assumptions" });
  await editor.getByLabel("Win probability (0 to 1)").fill("0.40");
  await editor.getByLabel("Probability source").fill("Synthetic likelihood change; half-time slots unchanged");
  await editor.getByLabel("Change reason").fill("Probability must not scale recruiting quantities");
  await editor.getByRole("button", { name: "Save revision", exact: true }).click();
  await expect(page.getByRole("region", { name: "Next opportunities", exact: true })).toContainText("Version 2");
  const sources = await request.get(`${api}/people/demand`, { headers });
  expect(sources.status()).toBe(200);
  const source = (await sources.json()).items.find((s: any) => s.plan_id === f.plan_id);
  expect(source.state).toBe("stale");
  const revised = await request.post(`${api}/people/demand/publications`, { headers, data: { ...f.publication_body,
    expected_source_version_id: source.source_version_id, expected_publication_version_id: source.publication_version_id,
    request_key: crypto.randomUUID(), reason: "Preserve half-time capacity after probability change", enrichments: {} } });
  expect(revised.status(), await revised.text()).toBe(201);
  await allocation("0.40");
  await sourcing(2);
  const historyResponse = await request.get(`${api}/people/sourcing/drafts?publication_id=${published.publication_id}`, { headers });
  expect(historyResponse.status()).toBe(200);
  const history = await historyResponse.json();
  expect(history.state).toBe("current");
  expect(history.items.map((d: any) => d.revision)).toEqual([2, 1]);
  expect(Number(history.items[0].snapshot.probability)).toBe(0.4);
  expect(Number(history.items[1].snapshot.probability)).toBe(0.7);
  expect(history.items[0].snapshot.rows).toEqual(history.items[1].snapshot.rows);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t22-part-time.png", fullPage: true });
});
