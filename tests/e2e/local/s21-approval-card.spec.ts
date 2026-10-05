import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("T40 in-review card and destination reconcile exact SOW packages, permissions and zero", async ({ page, request }) => {
  test.setTimeout(120_000);
  const run = randomUUID();
  const base = "http://127.0.0.1:8210";
  const root = resolve(process.cwd(), "../..");
  const headers = { "X-Test-User": `s21-t40-${run}@example.test` };
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const reviewers: string[] = [];
  for (let index = 0; index < 5; index++) {
    const reviewerHeaders = { "X-Test-User": `s21-t40-review-${index}-${run}@example.test` };
    const registered = await request.post(`${base}/dev/test-fixtures`, { headers: reviewerHeaders,
      data: { label: `T40 reviewer ${index} ${run}`, reviewer_ids: [] } });
    expect(registered.status()).toBe(201);
    const me = await request.get(`${base}/me`, { headers: reviewerHeaders });
    expect(me.status()).toBe(200);
    reviewers.push((await me.json()).id);
  }
  const own = await request.post(`${base}/dev/test-fixtures`, { headers,
    data: { label: `T40 owner ${run}`, reviewer_ids: reviewers } });
  expect(own.status(), await own.text()).toBe(201);
  const fixture = await own.json();
  const other = await request.post(`${base}/dev/test-fixtures`, {
    headers: { "X-Test-User": `s21-t40-hidden-${run}@example.test` },
    data: { label: `T40 hidden ${run}`, reviewer_ids: [] } });
  expect(other.status()).toBe(201);
  const hidden = await other.json();
  const inReview = async (pageNumber = 1, size = 100, revision?: string) => {
    const response = await request.get(`${base}/approvals/packages?status=in_review&page=${pageNumber}&size=${size}${revision ? `&population_revision=${revision}` : ""}`, { headers });
    expect(response.status()).toBe(200);
    return response.json();
  };
  const zero = await inReview();
  expect(zero.items).toEqual([]);
  expect(zero.population_revision).toMatch(/^[a-f0-9]{64}$/);
  await page.goto("/command");
  const card = page.getByTestId("banner-metric-sows_in_progress");
  await expect(card.locator("span").first()).toHaveText("0");
  await card.click();
  await expect(page).toHaveURL(new RegExp(`/sows\\?status=in_review&population_revision=${zero.population_revision}$`));
  await expect(page.getByText("No SOW packages yet.", { exact: true })).toBeVisible();
  await expect(page.locator('[data-testid^="sow-card-"]')).toHaveCount(0);
  const output = execFileSync(`${root}/api/.venv/bin/python`, ["scripts/s21_approval_card_fixture.py"], {
    cwd: root, encoding: "utf8", timeout: 30_000, env: { ...process.env,
      PYTHONPATH: `${root}/api:${root}`, POSTGRES_URL: "postgresql+asyncpg://s21@127.0.0.1:55421/s21_journey",
      DEALGATE_ENV: "local", DEALGATE_TENANT_ID: "s21-lead", S21_CARD_DEAL: fixture.opportunity_id,
      S21_CARD_HIDDEN_DEAL: hidden.opportunity_id, S21_CARD_REVIEWERS: JSON.stringify(reviewers) },
  });
  const source = JSON.parse(output.trim().split("\n").at(-1)!);
  const expected = [...source.included].sort();
  const rows = await inReview();
  expect(rows.total).toBe(2);
  expect(rows.items.map((p: { id: string }) => p.id).sort()).toEqual(expected);
  for (const pkg of rows.items) {
    expect(pkg.opportunity_id).toBe(fixture.opportunity_id);
    expect(pkg.assignments).toHaveLength(5);
    expect(new Set(pkg.assignments.map((a: { approver_id: string }) => a.approver_id)).size).toBe(5);
  }
  const first = await inReview(1, 1, rows.population_revision);
  const second = await inReview(2, 1, rows.population_revision);
  const third = await inReview(3, 1, rows.population_revision);
  expect([first.population_revision, second.population_revision, third.population_revision]).toEqual([
    rows.population_revision, rows.population_revision, rows.population_revision,
  ]);
  expect([first.total, second.total, third.total]).toEqual([2, 2, 2]);
  expect([...first.items, ...second.items].map(p => p.id).sort()).toEqual(expected);
  expect(third.items).toEqual([]);
  await page.goto("/command");
  await expect(card.locator("span").first()).toHaveText("2");
  await expect(card).toHaveAttribute("href", `/sows?status=in_review&population_revision=${rows.population_revision}`);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t40-card.png" });
  await card.click();
  await expect(page.getByRole("tab", { name: "In review", exact: true })).toHaveAttribute("aria-selected", "true");
  for (const id of expected) await expect(page.getByTestId(`sow-card-${id}`)).toBeVisible();
  await expect(page.locator('[data-testid^="sow-card-"]')).toHaveCount(2);
  for (const id of [source.approved, source.hidden]) await expect(page.getByTestId(`sow-card-${id}`)).toHaveCount(0);
  await expect(page.getByTestId("draft-sow-strip")).toHaveCount(0);
  await page.reload();
  for (const id of expected) await expect(page.getByTestId(`sow-card-${id}`)).toBeVisible();
  await expect(page.locator('[data-testid^="sow-card-"]')).toHaveCount(2);
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t40-list.png", fullPage: true });
  const stale = await request.get(`${base}/approvals/packages?status=in_review&population_revision=${zero.population_revision}`, { headers });
  expect(stale.status()).toBe(409);
  await page.goto(`/sows?status=in_review&population_revision=${zero.population_revision}`);
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.locator('[data-testid^="sow-card-"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Reload approvals", exact: true }).click();
  for (const id of expected) await expect(page.getByTestId(`sow-card-${id}`)).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator('[data-testid^="sow-card-"]')).toHaveCount(2);
});
