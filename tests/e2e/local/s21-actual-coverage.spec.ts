import { execFileSync, spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test("T21 Finance actuals replace certified scope, preserve bases and survive correction", async ({ page, request }) => {
  test.setTimeout(180_000);
  if (!process.env.S21_COV_MANIFEST) throw new Error("Require private T21 fixture manifest");
  const f = JSON.parse(readFileSync(process.env.S21_COV_MANIFEST, "utf8"));
  expect(f.database).toMatch(/^s21_cov_[0-9a-f]{32}$/);
  expect(f.tenant).toBe(f.database);
  const api = "http://127.0.0.1:8210";
  const headers = { "X-Test-User": f.actor_email };
  const sql = (query: string) => JSON.parse(execFileSync("docker", ["exec", "dealgate-s21-lead-db", "psql", "-U", "s21", "-d", f.database,
    "-At", "-v", "ON_ERROR_STOP=1", "-c", query], { encoding: "utf8", timeout: 20_000 }).trim());
  const count = () => sql(`SELECT count(*) FROM financial_actual WHERE original_account_id='${f.account_id}'`);
  const baseline = () => sql(`SELECT commercial_snapshot FROM gm_model WHERE id='${f.gm_model_id}'`);
  expect(count()).toBe(0);
  const frozen = baseline();
  const source = `t21-coverage-${crypto.randomUUID()}`;
  const base = { account_id: f.account_id, gm_model_id: f.gm_model_id, period_month: f.month,
    source_date: f.cutoff, currency: "USD", revision: 1, expected_previous_revision: 0,
    reason: "Synthetic Finance-confirmed source, no live connector" };
  const coverage = { sow_version_id: f.sow_version_id, schedule_row: 0,
    fraction_start: "0", fraction_end: "0.5", through_date: f.cutoff,
    basis_evidence: "Finance explicitly certifies the first half of this signed service scope on the same accounting basis" };
  const amounts = { recognized_revenue: "11000.99", delivery_cost: "6000", billed: "15000", cash_collected: "8000" };
  const original = { source_system: source, idempotency_key: crypto.randomUUID(), rows: Object.entries(amounts).map(([measure, amount]) =>
    ({ ...base, source_id: measure, measure, amount })) };
  const imported = await request.post(`${api}/actuals/financial-import`, { headers, data: original });
  expect(imported.status(), await imported.text()).toBe(201);
  const firstId = (await imported.json()).id;
  const replay = await request.post(`${api}/actuals/financial-import`, { headers, data: original });
  expect(replay.status()).toBe(201);
  expect((await replay.json()).id).toBe(firstId);
  expect(count()).toBe(4);
  // Actual imports bind JSON null; a reversible empty-coverage migration must remain safe.
  expect(sql(`SELECT count(*) FROM financial_actual WHERE original_account_id='${f.account_id}' AND coverage='null'::jsonb`)).toBe(4);
  const env = { ...process.env, POSTGRES_URL: `postgresql+asyncpg://s21@127.0.0.1:55421/${f.database}` };
  const migration = (direction: string, target: string) => execFileSync(".venv/bin/alembic", [direction, target], { cwd: "../../api", env, encoding: "utf8", timeout: 30_000 });
  migration("downgrade", "20261002_0061_automation_jobs");
  migration("upgrade", "head");
  expect(count()).toBe(4);

  await page.route("**/api/**", route => route.continue({ headers: { ...route.request().headers(), ...headers } }));
  await page.goto(`/forecast?view=overview&account_id=${f.account_id}`);
  const estimate = page.getByRole("region", { name: "Current-period signed estimate", exact: true });
  await expect(estimate).toBeVisible();
  await expect(estimate.getByText("No matched actuals", { exact: true })).toHaveCount(2);
  const pre = await request.get(`${api}/forecast/outlook?account_id=${f.account_id}`, { headers });
  expect(pre.status(), await pre.text()).toBe(200);
  const before = await pre.json();
  expect(before.current_period_estimate.totals.revenue).toBe("24000");
  expect(before.current_period_estimate.totals.cost).toBe("10000");
  const matched = { source_system: source, idempotency_key: crypto.randomUUID(), rows: original.rows.slice(0, 2).map(row =>
    ({ ...row, revision: 2, expected_previous_revision: 1, coverage })) };
  const bound = await request.post(`${api}/actuals/financial-import`, { headers, data: matched });
  expect(bound.status(), await bound.text()).toBe(201);
  await page.reload();
  const revenue = estimate.getByRole("row").filter({ hasText: "Recognized revenue" });
  const cost = estimate.getByRole("row").filter({ hasText: "Delivery cost" });
  await expect(revenue.getByRole("cell").nth(3)).toHaveText("24000");
  await expect(revenue.getByRole("cell").nth(4)).toHaveText("11000.99");
  await expect(revenue.getByRole("cell").nth(5)).toHaveText("50.0%");
  await expect(revenue.getByRole("cell").nth(6)).toHaveText("12000");
  await expect(revenue.getByRole("cell").nth(7)).toHaveText("23000.99");
  await expect(cost.getByRole("cell").nth(4)).toHaveText("6000");
  await expect(cost.getByRole("cell").nth(6)).toHaveText("5000");
  await expect(cost.getByRole("cell").nth(7)).toHaveText("11000");
  const check = await request.get(`${api}/forecast/outlook?account_id=${f.account_id}`, { headers });
  expect(check.status()).toBe(200);
  const after = await check.json();
  expect(after.current_month).toEqual(before.current_month);
  expect(after.current_period_estimate.totals.profit).toBe("12000.99");
  expect(Object.fromEntries(after.financial_actuals.totals.map((row: any) => [row.measure, row.amount]))).toEqual(amounts);
  const financial = page.getByRole("region", { name: "Financial actuals", exact: true });
  await expect(financial.getByRole("row").filter({ hasText: "Billed" })).toContainText("15000");
  await expect(financial.getByRole("row").filter({ hasText: "Cash collected" })).toContainText("8000");
  await page.screenshot({ path: "../../docs/s21/evidence/baseline/t21-coverage.png", fullPage: true });

  const corrected = { source_system: source, idempotency_key: crypto.randomUUID(), rows: [{ ...matched.rows[0],
    revision: 3, expected_previous_revision: 2, amount: "10500", reason: "Finance correction preserves covered service scope" }] };
  const changed = await request.post(`${api}/actuals/financial-import`, { headers, data: corrected });
  expect(changed.status(), await changed.text()).toBe(201);
  await page.reload();
  await expect(revenue.getByRole("cell").nth(7)).toHaveText("22500");
  await expect(cost.getByRole("cell").nth(7)).toHaveText("11000");
  expect(baseline()).toEqual(frozen);
  expect(sql(`SELECT json_agg(amount::text ORDER BY revision) FROM financial_actual WHERE original_account_id='${f.account_id}' AND measure='recognized_revenue'`))
    .toEqual(["11000.99", "11000.99", "10500"]);

  const raceBody = (system: string) => ({ source_system: system, idempotency_key: crypto.randomUUID(), rows: [{ ...base,
    source_id: "adjacent-scope", measure: "recognized_revenue", amount: "100", coverage: { ...coverage, fraction_start: "0.5", fraction_end: "0.75" } }] });
  const racing = [raceBody(`${source}-a`), raceBody(`${source}-b`)];
  const beforeRace = count();
  const barrier = spawn("docker", ["exec", "dealgate-s21-lead-db", "psql", "-U", "s21", "-d", f.database, "-v", "ON_ERROR_STOP=1", "-c",
    `BEGIN; SELECT id FROM client WHERE id='${f.account_id}' FOR UPDATE; SELECT pg_sleep(8) /* s21_t21_barrier */; COMMIT;`]);
  const barrierDone = new Promise<number | null>((resolve, reject) => { barrier.on("error", reject); barrier.on("close", resolve); });
  await expect.poll(() => sql("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event='PgSleep' AND query LIKE '%s21_t21_barrier%'"), { timeout: 5000 }).toBe(1);
  const blocker = sql("SELECT pid FROM pg_stat_activity WHERE datname=current_database() AND wait_event='PgSleep' AND query LIKE '%s21_t21_barrier%'");
  const pending = racing.map((data, index) => request.post(`${api}/actuals/financial-import`, { data,
    headers: { "X-Test-User": index === 0 ? f.actor_email : f.second_email } }));
  const waiters = () => sql("SELECT COALESCE(json_agg(json_build_object('pid',pid,'query',query,'blockers',pg_blocking_pids(pid))), '[]'::json) FROM pg_stat_activity WHERE datname=current_database() AND cardinality(pg_blocking_pids(pid))>0");
  await expect.poll(() => waiters().filter((row: any) => row.query.includes("client.id") && row.query.includes("FOR UPDATE")).length, { timeout: 5000 }).toBe(2);
  const waiting = waiters();
  expect(waiting).toHaveLength(2);
  for (const row of waiting) {
    expect(row.query).toContain("client.id");
    expect(row.query).toContain("FOR UPDATE");
    expect(row.blockers.some((pid: number) => pid === blocker || waiting.some((other: any) => other.pid === pid && other.blockers.includes(blocker)))).toBe(true);
  }
  const responses = await Promise.all(pending);
  expect(await barrierDone).toBe(0);
  expect(responses.map(response => response.status()).sort()).toEqual([201, 422]);
  const loser = responses.find(response => response.status() === 422)!;
  expect(await loser.text()).toContain("Coverage overlaps another current actual source");
  expect(count()).toBe(beforeRace + 1);
  const winner = responses.findIndex(response => response.status() === 201);
  expect(sql(`SELECT json_build_object('source_system',source_system,'amount',amount::text,'start',coverage->>'fraction_start','end',coverage->>'fraction_end') FROM financial_actual WHERE original_account_id='${f.account_id}' AND source_id='adjacent-scope'`))
    .toEqual({ source_system: racing[winner].source_system, amount: "100", start: "0.5", end: "0.75" });
  const removedCoverage = { ...racing[winner], idempotency_key: crypto.randomUUID(), rows: [{ ...racing[winner].rows[0],
    revision: 2, expected_previous_revision: 1, coverage: null, reason: "Retain separate actual pending basis review" }] };
  const unbound = await request.post(`${api}/actuals/financial-import`, { headers, data: removedCoverage });
  expect(unbound.status(), await unbound.text()).toBe(201);
  await page.reload();
  await expect(revenue.getByRole("cell").nth(7)).toHaveText("22500");
  expect(baseline()).toEqual(frozen);
  let downgradeRefused = false;
  try { migration("downgrade", "20261002_0061_automation_jobs"); }
  catch (error) { downgradeRefused = String(error).includes("Cannot discard immutable financial coverage history"); }
  expect(downgradeRefused).toBe(true);
  expect(sql("SELECT to_json(version_num) FROM alembic_version")).toBe("20261003_0062_actual_coverage");
  writeFileSync("../../docs/s21/evidence/baseline/t21-coverage-proof.json", JSON.stringify({ database: f.database,
    fixture_boundary: f.fixture_boundary, before, after, race_statuses: responses.map(response => response.status()), blocker, waiting,
    baseline_unchanged: true, final_rows: count(), migration_history_guard: true }, null, 2));
});
