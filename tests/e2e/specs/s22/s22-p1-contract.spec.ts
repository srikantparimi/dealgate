/**
 * S22 P1-5 · contract test on the deployed API.
 *
 * Seeds the Client A golden (docs/reference/forecast-goldens.json) under an
 * S22 e2e run tag through the real endpoints, then asserts that
 * `GET /engagements/{id}/forecast` reproduces the goldens' expected totals
 * and month-by-assignment rows to the cent. Nothing is mocked: this drives
 * Cognito → CloudFront → ALB → ECS → RDS → the forecast engine.
 *
 * Teardown is unconditional (afterAll): the tagged client is hard-deleted
 * (its engagement, allocations, costs and forecast runs cascade) and the
 * tagged people are removed, so `scripts/check-test-data-clean.sh` finds 0
 * leaks afterwards.
 *
 *   E2E_BASE_URL=https://app.dealgateapp.com npx playwright test specs/s22/s22-p1-contract.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { bearerFor } from "../../fixtures/multi-role-auth";

const BASE = process.env.E2E_BASE_URL ?? "https://app.dealgateapp.com";
// Local full-stack runs (uvicorn + Vite, DEALGATE_ENV=local): identity comes from the
// X-Test-User header / VITE_TEST_USER instead of Cognito. Unset on staging.
const LOCAL_USER = process.env.E2E_LOCAL_USER;
const API_BASE = process.env.E2E_API_BASE ? `${process.env.E2E_API_BASE}/` : `${BASE}/api/`;
const authHeaders = (): Record<string, string> => (LOCAL_USER ? { "X-Test-User": LOCAL_USER } : bearerFor("system"));
const REPO = path.resolve(__dirname, "..", "..", "..", "..");
const GOLDENS = JSON.parse(fs.readFileSync(path.join(REPO, "docs/reference/forecast-goldens.json"), "utf8"));
const RUN_TAG = `S22 e2e ${Date.now()}`;

const TYPE: Record<string, string> = {
  "Fixed cost": "fixed_cost",
  Assessment: "assessment",
  MSP: "msp",
  "Time & materials": "time_and_materials",
  "Staff augmentation": "staff_augmentation",
};
const EMP: Record<string, string> = { "W-2 / Employee": "w2_employee", "1099 / Contractor": "contractor_1099" };

type Scenario = {
  name: string;
  engagement_type: string;
  start: string;
  end: string;
  total_price: number | null;
  monthly_fee: number | null;
  additional_costs_flag: "Y" | "N";
  same_dates_for_all: boolean;
  additional_costs: { amount: number; frequency: string; billed_to_client: "Y" | "N" }[];
  allocations: {
    role: string;
    location: string;
    employment_type: string;
    assignment: string | null;
    utilization: number;
    bill_rate: number | null;
    cost_per_hour: number;
    start: string;
    end: string;
    hours_override: number | null;
    expected: { working_days: number; hours: number; labour_cost: number; burden_cost: number; revenue: number };
  }[];
  expected: Record<string, number | string | boolean | null>;
  expected_monthly_by_assignment: { month: string; assignment: string; people: number; hours: number; revenue: number; loaded_cost: number }[];
};

const CLIENT_A: Scenario = GOLDENS.scenarios.find((s: Scenario) => s.name.startsWith("STAFF AUG — Client A"));

function closeTo(actual: unknown, expected: unknown, tolerance = 0.01): void {
  expect(Math.abs(Number(actual) - Number(expected)), `${actual} vs ${expected}`).toBeLessThanOrEqual(tolerance);
}

async function json<T>(response: import("@playwright/test").APIResponse): Promise<T> {
  if (!response.ok()) {
    throw new Error(`${response.status()} ${response.url()}\n${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

/**
 * S21 runtime isolation: a test identity may only touch accounts the server
 * issued to it through POST /dev/test-fixtures (and DELETE /clients refuses
 * anything else). Locally, where the dev-seed endpoint is off, fall back to
 * POST /clients.
 */
async function issueFixtureClient(ctx: APIRequestContext, label: string): Promise<{ id: string; name: string; fixture: boolean }> {
  const issued = await ctx.post("dev/test-fixtures", { data: { label, reviewer_ids: [] } });
  if (issued.ok()) {
    const body = (await issued.json()) as { client_id: string; client_name?: string };
    const detail = await ctx.get(`clients/${body.client_id}`);
    const name = detail.ok() ? ((await detail.json()) as { name: string }).name : body.client_name ?? label;
    return { id: body.client_id, name, fixture: true };
  }
  const created = await ctx.post("clients", { data: { name: label } });
  if (!created.ok()) throw new Error(`${created.status()} creating client: ${await created.text()}`);
  const body = (await created.json()) as { id: string; name: string };
  return { id: body.id, name: body.name, fixture: false };
}

async function deleteClientAndWait(ctx: APIRequestContext, clientId: string, reason: string): Promise<boolean> {
  const del = await ctx.delete(`clients/${clientId}`, { params: { reason } });
  if (!del.ok()) {
    console.warn(`[s22 teardown] DELETE clients/${clientId} -> ${del.status()} ${await del.text()}`);
    return false;
  }
  const body = (await del.json().catch(() => ({}))) as { job_id?: string };
  for (let attempt = 0; body.job_id && attempt < 60; attempt += 1) {
    const state = (await (await ctx.get(`deletion-jobs/${body.job_id}`)).json()) as { status: string };
    if (state.status === "done" || state.status === "failed") break;
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
  return true;
}

let api: APIRequestContext;
let clientId: string | null = null;
const resourceIds: string[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  api = await pwRequest.newContext({
    baseURL: API_BASE,
    extraHTTPHeaders: authHeaders(),
    timeout: 90_000,
  });
});

test.afterAll(async () => {
  // Teardown always runs — pass, fail or timeout.
  try {
    // Order matters: the client delete cascades the engagement and its allocations; only then can people go.
    if (clientId) await deleteClientAndWait(api, clientId, "S22 P1 contract teardown");
    for (const id of resourceIds) {
      await api.delete(`resources/${id}`).catch(() => undefined);
    }
    // Nothing tagged may survive on staging.
    const clients = (await (await api.get("clients?size=200")).json()) as { items?: { id: string; name: string }[] };
    const leaked = (clients.items ?? []).filter((c) => c.name.includes(RUN_TAG));
    for (const c of leaked) await api.delete(`clients/${c.id}?reason=S22%20leak%20sweep`).catch(() => undefined);
    const people = (await (await api.get("resources")).json()) as { id: string; name: string }[];
    for (const p of people.filter((r) => r.name.includes(RUN_TAG))) await api.delete(`resources/${p.id}`).catch(() => undefined);
    const left = (await (await api.get("engagements?page_size=100")).json()) as { items?: { name: string; client_name: string }[] };
    const leakedEngagements = (left.items ?? []).filter((e) => `${e.name} ${e.client_name}`.includes(RUN_TAG));
    if (leakedEngagements.length) console.error(`[s22 teardown] ${leakedEngagements.length} engagement(s) still carry ${RUN_TAG}`);
  } finally {
    await api.dispose();
  }
});

test("S22 P1-5 · Client A golden through the deployed API equals the goldens to the cent", async () => {
  const sc = CLIENT_A;
  const client = await issueFixtureClient(api, `${RUN_TAG} Client A`);
  clientId = client.id;

  const engagement = await json<{ id: string; status: string; duration_months: number }>(
    await api.post("engagements", {
      data: {
        client_id: client.id,
        name: `${RUN_TAG} Portal & data platform staffing`,
        type: TYPE[sc.engagement_type],
        start: sc.start,
        end: sc.end,
        total_price: sc.total_price,
        monthly_fee: sc.monthly_fee,
        additional_costs_flag: sc.additional_costs_flag === "Y",
        same_dates_for_all: sc.same_dates_for_all,
      },
    }),
  );
  closeTo(engagement.duration_months, sc.expected.duration_months, 0.000001);

  const created: { id: string }[] = [];
  for (const [index, row] of sc.allocations.entries()) {
    const resource = await json<{ id: string }>(
      await api.post("resources", {
        data: {
          name: `${RUN_TAG} ${row.role} ${index + 1}`,
          location: row.location,
          employment_type: EMP[row.employment_type],
          seniority: "Mid",
        },
      }),
    );
    resourceIds.push(resource.id);
    created.push(
      await json<{ id: string }>(
        await api.post(`engagements/${engagement.id}/allocations`, {
          data: {
            resource_id: resource.id,
            role: row.role,
            assignment: row.assignment,
            utilization: row.utilization,
            bill_rate: row.bill_rate,
            cost_per_hour: row.cost_per_hour,
            start: row.start,
            end: row.end,
            hours_override: row.hours_override,
          },
        }),
      ),
    );
  }
  for (const cost of sc.additional_costs) {
    await json(
      await api.post(`engagements/${engagement.id}/costs`, {
        data: {
          description: "golden cost",
          amount: cost.amount,
          frequency: cost.frequency === "Monthly" ? "monthly" : "one_time",
          billed_to_client: cost.billed_to_client === "Y",
        },
      }),
    );
  }

  type Forecast = {
    status: string;
    monthly_required: boolean;
    missing: string[];
    duration_months: number;
    totals: Record<string, string | number | null>;
    months: { total_revenue: string; total_cost: string }[];
    by_assignment: Record<string, Record<string, { people: number; hours: number; revenue: string; loaded_cost: string }>>;
    allocation_months: { allocation_id: string; working_days: number; hours: number; revenue: string; loaded_cost: string; resource_name: string }[];
    location_check: Record<string, { ok: boolean; revenue: string }>;
  };
  const forecast = await json<Forecast>(await api.get(`engagements/${engagement.id}/forecast`));
  const e = sc.expected;
  expect(forecast.status).toBe(e.status);
  expect(forecast.monthly_required).toBe(e.monthly_required);
  expect(forecast.missing).toEqual([]);
  closeTo(forecast.duration_months, e.duration_months, 0.000001);
  closeTo(forecast.totals.hours, e.hours, 0.001);
  for (const key of ["labour_cost", "burden_cost", "additional_costs", "pass_through_revenue", "total_revenue", "total_cost"]) {
    closeTo(forecast.totals[key], e[key]);
  }
  closeTo(forecast.totals.gm_pct, e.gm_pct, 0.000001);

  // month × assignment rows, to the cent
  for (const row of sc.expected_monthly_by_assignment) {
    const got = forecast.by_assignment[row.assignment][row.month];
    expect(got, `${row.assignment} ${row.month}`).toBeTruthy();
    expect(got.people).toBe(row.people);
    closeTo(got.hours, row.hours, 0.001);
    closeTo(got.revenue, row.revenue);
    closeTo(got.loaded_cost, row.loaded_cost);
  }

  // per-allocation expectations through allocation_months
  for (const [index, row] of sc.allocations.entries()) {
    const mine = forecast.allocation_months.filter((am) => am.allocation_id === created[index].id);
    expect(mine.reduce((acc, am) => acc + am.working_days, 0)).toBe(row.expected.working_days);
    closeTo(mine.reduce((acc, am) => acc + am.hours, 0), row.expected.hours, 0.001);
    closeTo(mine.reduce((acc, am) => acc + Number(am.revenue), 0), row.expected.revenue);
    closeTo(mine.reduce((acc, am) => acc + Number(am.loaded_cost), 0), row.expected.labour_cost + row.expected.burden_cost);
    expect(mine.every((am) => am.resource_name.includes(RUN_TAG))).toBe(true);
  }

  // the monthly lines reconcile to the totals
  closeTo(forecast.months.reduce((acc, m) => acc + Number(m.total_revenue), 0), forecast.totals.total_revenue, 0.01);
  closeTo(forecast.months.reduce((acc, m) => acc + Number(m.total_cost), 0), forecast.totals.total_cost, 0.01);
  expect(forecast.location_check.US.ok).toBe(false);
  expect(forecast.location_check.India.ok).toBe(true);

  // the engagement shows up in its portfolio month with the same numbers
  const portfolio = await json<{ rows: { engagement_id: string; revenue_month: string; status: string }[]; cards: { below_floor: number } }>(
    await api.get("portfolio/forecast", { params: { month: "2027-01", client_id: client.id } }),
  );
  const row = portfolio.rows.find((r) => r.engagement_id === engagement.id);
  expect(row?.status).toBe("PASS");
  const january = sc.expected_monthly_by_assignment.filter((r) => r.month === "2027-01").reduce((acc, r) => acc + r.revenue, 0);
  // January revenue = Σ assignment revenue + the monthly pass-through share (none in January: the one-time cost lands in month 1)
  closeTo(row?.revenue_month, january, 0.01);
});
