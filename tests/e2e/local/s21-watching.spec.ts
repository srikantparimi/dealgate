import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

test("T39 Watching is zero, one exact deal in three groups, then zero with access filtering", async ({ page, request }) => {
  test.setTimeout(120_000);
  const run = randomUUID();
  const email = `s21-t39-${run}@example.test`;
  const headers = { "X-Test-User": email };
  const base = "http://127.0.0.1:8210";
  // Local identity adapter only: all feature requests reach the real API/DB.
  await page.route("**/api/**", route => route.continue({
    headers: { ...route.request().headers(), "X-Test-User": email },
  }));
  const fixtureResponse = await request.post(`${base}/dev/test-fixtures`, { headers,
    data: { label: `T39 owner ${run}`, reviewer_ids: [] } });
  expect(fixtureResponse.status()).toBe(201);
  const fixture = await fixtureResponse.json();
  const hiddenResponse = await request.post(`${base}/dev/test-fixtures`, {
    headers: { "X-Test-User": `s21-t39-hidden-${run}@example.test` },
    data: { label: `T39 inaccessible ${run}`, reviewer_ids: [] },
  });
  expect(hiddenResponse.status()).toBe(201);
  const hidden = await hiddenResponse.json();
  const groups: string[] = [];
  const proof = process.env.S21_WATCHING_PROOF_PREFIX ?? "t39-watching";
  const watchState = async () => {
    const response = await request.get(`${base}/watchlist`, { headers });
    expect(response.status()).toBe(200);
    return response.json();
  };
  const pipelineState = async () => {
    const response = await request.get(`${base}/pipeline/opportunities?watching=true`, { headers });
    expect(response.status()).toBe(200);
    return response.json();
  };
  try {
    expect((await watchState()).matching_deal_count).toBe(0);
    await page.goto("/command");
    const card = page.getByTestId("banner-metric-watching");
    await expect(card).toBeVisible();
    await expect(card.locator("span").first()).toHaveText("0");
    await card.click();
    await expect(page.getByRole("tab", { name: "Opportunities (0)", exact: true })).toBeVisible();
    expect((await pipelineState()).items).toEqual([]);
    for (let i = 0; i < 3; i++) {
      const created = await request.post(`${base}/tracking-groups`, { headers,
        data: { name: `T39 ${run} group ${i}`, member_kind: "opportunity", visibility: "private" } });
      expect(created.status()).toBe(201);
      const group = await created.json();
      groups.push(group.id);
      const members = await request.post(`${base}/tracking-groups/${group.id}/members`, { headers,
        data: { member_ids: [fixture.opportunity_id] } });
      expect(members.status()).toBe(200);
      expect((await members.json()).member_ids).toEqual([fixture.opportunity_id]);
    }
    await page.goto(`/deals/${fixture.opportunity_id}`);
    const star = page.getByTestId(`watch-star-opportunity-${fixture.opportunity_id}`);
    await expect(star).toHaveAttribute("aria-pressed", "false");
    await star.click();
    await expect(star).toHaveAttribute("aria-pressed", "true");
    expect((await watchState()).items.map((r: { item_id: string }) => r.item_id)).toEqual([fixture.opportunity_id]);
    expect((await watchState()).matching_deal_count).toBe(1);
    const denied = await request.post(`${base}/watchlist`, { headers,
      data: { kind: "opportunity", item_id: hidden.opportunity_id } });
    expect(denied.status()).toBe(404);
    expect((await request.get(`${base}/pipeline/opportunities/${hidden.opportunity_id}`, { headers })).status()).toBe(404);
    const rows = await pipelineState();
    expect(rows.total).toBe(1);
    expect(rows.items.map((r: { opportunity_id: string }) => r.opportunity_id)).toEqual([fixture.opportunity_id]);
    const grouped = await request.get(`${base}/pipeline/opportunities?watching=true&${groups.map(id => `group=${id}`).join("&")}`, { headers });
    expect(grouped.status()).toBe(200);
    const groupedRows = await grouped.json();
    expect(groupedRows.total).toBe(1);
    expect(groupedRows.items.map((r: { opportunity_id: string }) => r.opportunity_id)).toEqual([fixture.opportunity_id]);
    await page.goto("/command");
    await expect(card.locator("span").first()).toHaveText("1");
    await page.screenshot({ path: `../../docs/s21/evidence/baseline/${proof}-one.png` });
    await card.click();
    await page.getByRole("tab", { name: "Opportunities (1)", exact: true }).click();
    await expect(page.getByTestId(`opp-row-${fixture.opportunity_id}`)).toBeVisible();
    await expect(page.locator('[data-testid^="opp-row-"]')).toHaveCount(1);
    await expect(page.getByTestId(`opp-row-${hidden.opportunity_id}`)).toHaveCount(0);
    await page.screenshot({ path: `../../docs/s21/evidence/baseline/${proof}-list.png` });
    await page.goto(`/deals/${fixture.opportunity_id}`);
    await expect(star).toHaveAttribute("aria-pressed", "true");
    await star.click();
    await expect(star).toHaveAttribute("aria-pressed", "false");
    expect((await watchState()).matching_deal_count).toBe(0);
    expect((await pipelineState()).items).toEqual([]);
    await page.goto("/command");
    await expect(card.locator("span").first()).toHaveText("0");
    await card.click();
    await page.getByRole("tab", { name: "Opportunities (0)", exact: true }).click();
    await expect(page.locator('[data-testid^="opp-row-"]')).toHaveCount(0);
    await page.screenshot({ path: `../../docs/s21/evidence/baseline/${proof}-empty.png` });
  } finally {
    await request.delete(`${base}/watchlist?kind=opportunity&item_id=${fixture.opportunity_id}`, { headers });
    for (const id of groups) expect((await request.delete(`${base}/tracking-groups/${id}`, { headers })).status()).toBe(204);
    expect((await watchState()).items).toEqual([]);
  }
});

test("Watching count and exact client-group membership follow current search filters", async ({ page, request }) => {
  test.setTimeout(90_000);
  const run = randomUUID();
  const headers = { "X-Test-User": `s21-watch-filter-${run}@example.test` };
  const base = "http://127.0.0.1:8210";
  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  const issued = await request.post(`${base}/dev/test-fixtures`, { headers,
    data: { label: `Watching filter ${run}`, reviewer_ids: [] } });
  expect(issued.status()).toBe(201);
  const fixture = await issued.json();
  const created = await request.post(`${base}/tracking-groups`, { headers,
    data: { name: `Watching client ${run}`, member_kind: "client", visibility: "private" } });
  expect(created.status()).toBe(201);
  const group = await created.json();
  try {
    expect((await request.post(`${base}/tracking-groups/${group.id}/members`, { headers,
      data: { member_ids: [fixture.client_id] } })).status()).toBe(200);
    expect((await request.post(`${base}/watchlist`, { headers,
      data: { kind: "opportunity", item_id: fixture.opportunity_id } })).status()).toBe(201);
    await page.goto(`/pipeline?watching=true&view=opportunities&group=${group.id}`);
    await expect(page.getByRole("checkbox", { name: "Watching (1)", exact: true })).toBeChecked();
    await expect(page.getByTestId(`opp-row-${fixture.opportunity_id}`)).toBeVisible();
    await expect(page.locator('[data-testid^="opp-row-"]')).toHaveCount(1);
    await page.getByRole("searchbox", { name: "Search deal or client", exact: true }).fill(`no-match-${run}`);
    await page.getByRole("searchbox", { name: "Search deal or client", exact: true }).press("Enter");
    await expect(page.getByRole("checkbox", { name: "Watching (0)", exact: true })).toBeChecked();
    await expect(page.getByRole("tab", { name: "Opportunities (0)", exact: true })).toBeVisible();
    await expect(page.locator('[data-testid^="opp-row-"]')).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("checkbox", { name: "Watching (0)", exact: true })).toBeChecked();
    await page.getByRole("button", { name: `Remove Search: no-match-${run}`, exact: true }).click();
    await expect(page.getByRole("checkbox", { name: "Watching (1)", exact: true })).toBeChecked();
    await expect(page.getByTestId(`opp-row-${fixture.opportunity_id}`)).toBeVisible();
    const response = await request.get(`${base}/pipeline/opportunities?watching=true&group=${group.id}`, { headers });
    expect(response.status()).toBe(200);
    expect((await response.json()).items.map((r: { opportunity_id: string }) => r.opportunity_id)).toEqual([fixture.opportunity_id]);
  } finally {
    expect((await request.delete(`${base}/watchlist?kind=opportunity&item_id=${fixture.opportunity_id}`, { headers })).status()).toBe(204);
    expect((await request.delete(`${base}/tracking-groups/${group.id}`, { headers })).status()).toBe(204);
  }
});
