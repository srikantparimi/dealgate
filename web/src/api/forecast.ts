import { request } from "./client";

import type { CommercialComponent } from "./commercial";
export type ForecastScenario = "committed" | "expected" | "upside";
export interface ForecastFilters {
  scenario: ForecastScenario;
  future_quarters: 1 | 2 | 4;
  account_id?: string;
  as_of?: string;
}
export interface ForecastPeriod {
  start: string;
  end_exclusive: string;
  revenue: string;
  signed: string;
  potential: string;
  expected: string;
  cost?: string | null;
  known_cost?: string;
  cost_complete?: boolean;
  gm?: string | null;
  signed_coverage?: string | null;
  provisional?: string;
  unavoidable_cost?: string;
}
export interface ForecastAccount {
  account_id: string;
  name: string;
  current_month: ForecastPeriod;
  current_quarter: ForecastPeriod;
  future: ForecastPeriod;
  quarters: ForecastPeriod[];
}
export interface ForecastRow {
  source_name?: string;
  calculation_version?: string;
  assumptions?: string[];
  source_evidence?: string[];
  opportunity_id?: string | null;
  source_url?: string | null;
  row_id: string;
  account_id: string;
  source_id: string;
  source_version: string;
  scope_id: string;
  month: string;
  lifecycle: string;
  revenue: string;
  signed: string;
  potential: string;
  currency: string;
  cost?: string | null;
  probability?: string | null;
  original_currency?: string;
  fx_version?: string | null;
  fx_date?: string | null;
}
export interface ForecastOutlook {
  schema_version: string;
  as_of: string;
  timezone: string;
  currency: string;
  scenario: ForecastScenario;
  future_quarters: number;
  current_month: ForecastPeriod;
  current_quarter: ForecastPeriod;
  future: ForecastPeriod;
  quarters: ForecastPeriod[];
  accounts: ForecastAccount[];
  months: ForecastPeriod[];
  rows: ForecastRow[];
  excluded: {
    source_name?: string;
    row_id: string;
    source_id: string;
    account_id: string;
    month: string;
    reasons: string[];
  }[];
  unresolved_sources: {
    source_id: string;
    source_version: string;
    account_id: string;
    name: string;
    reasons: string[];
  }[];
  pending_sources: string[];
  source_watermark: string;
  scope_label: string;
  source_count: number;
  stale: boolean;
  source_coverage: string;
  legacy_sources_included: boolean;
  actuals_available: boolean;
  actuals_basis: string;
  financial_actuals?: {
    totals: { period_month: string; measure: string; currency: string; amount: string }[];
    excluded: { id: string | null; reason: string }[];
    cutoff: string;
    blended_with_forecast: false;
  };
  current_period_estimate?: {
    cutoff: string;
    currency: string;
    totals: { revenue: string | null; cost: string | null; profit: string | null; gm_pct: string | null };
    excluded: { id: string | null; reason: string }[];
    rows: {
      row_id: string; source_id: string; source_version: string; account_id: string; month: string;
      revenue: CoverageMeasure; cost: CoverageMeasure;
    }[];
  };
}
export interface CoverageMeasure {
  scheduled: string | null;
  actual_to_date: string;
  covered_fraction: string;
  uncovered_forecast: string | null;
  estimate: string | null;
  actual_ids: string[];
}
export interface ForecastPlan {
  can_edit_assumptions?: boolean;
  source_evidence?: string[];
  id: string;
  version_id: string;
  version: number;
  account_id: string;
  account_name: string | null;
  opportunity_id: string | null;
  source_status: string;
  owner_id: string;
  title: string;
  lifecycle: string;
  probability: string | null;
  probability_source: string | null;
  assumptions: string[];
  scope_id: string;
  commercial_inputs?: CommercialComponent;
  job: {
    id: string;
    status: string;
    attempts: number;
    next_attempt_at: string | null;
    last_error: string | null;
  } | null;
}
export interface ForecastPlans {
  items: ForecastPlan[];
  total: number;
  page: number;
  size: number;
}
export interface ForecastAssumptions {
  expected_version_id: string;
  probability: string | null;
  probability_source: string | null;
  assumptions: string[];
  lifecycle:
    | "needs_review"
    | "tentative"
    | "won_unsigned"
    | "closed_lost"
    | "dismissed"
    | "expired";
  change_reason: string;
}
export const reviseForecastAssumptions = (
  planId: string,
  body: ForecastAssumptions,
) =>
  request<{ id: string; version_id: string; version: number }>(
    `/forecast/plans/${encodeURIComponent(planId)}/assumptions`,
    { method: "POST", body: JSON.stringify(body) },
  );
export const reviseForecastCommercial = (planId: string, body: {
  expected_version_id: string; inputs: CommercialComponent; change_reason: string;
}) => request<{ id: string; version_id: string; version: number }>(
  `/forecast/plans/${encodeURIComponent(planId)}/commercial`,
  { method: "POST", body: JSON.stringify(body) },
);
function query(values: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return params.toString();
}
export const getForecastOutlook = (
  filters: ForecastFilters,
  signal?: AbortSignal,
) =>
  request<ForecastOutlook>(`/forecast/outlook?${query({ ...filters })}`, {
    signal,
  });
export const getForecastPlans = (
  filters: { account_id?: string; page: number; size: number },
  signal?: AbortSignal,
) => request<ForecastPlans>(`/forecast/plans?${query(filters)}`, { signal });

/** Export only caller-selected authorized server rows, preserving Decimal text. */
export function forecastCsv(
  rows: ForecastRow[],
  outlook: ForecastOutlook,
): string {
  const fields = [
    "account_id",
    "source_id",
    "source_version",
    "scope_id",
    "month",
    "lifecycle",
    "currency",
    "signed",
    "potential",
    "revenue",
  ] as const;
  const hasCosts = rows.some((row) =>
    Object.prototype.hasOwnProperty.call(row, "cost"),
  );
  const cell = (value: unknown) => {
    const text = String(value ?? "");
    return `"${(/^[\s]*[=+\-@]/.test(text) ? "'" + text : text).replace(/"/g, '""')}"`;
  };
  return [
    [
      ...fields,
      "account_name",
      "source_name",
      "calculation_version",
      ...(hasCosts ? ["cost"] : []),
      "scenario",
      "as_of",
      "timezone",
      "original_currency",
      "fx_version",
      "fx_date",
      "scope",
      "source_watermark",
    ]
      .map(cell)
      .join(","),
    ...rows.map((row) =>
      [
        ...fields.map((field) => row[field]),
        outlook.accounts.find(
          (account) => account.account_id === row.account_id,
        )?.name ?? "",
        row.source_name ?? "",
        row.calculation_version ?? "",
        ...(hasCosts ? [row.cost ?? ""] : []),
        outlook.scenario,
        outlook.as_of,
        outlook.timezone,
        row.original_currency ?? "",
        row.fx_version ?? "",
        row.fx_date ?? "",
        outlook.scope_label,
        outlook.source_watermark,
      ]
        .map(cell)
        .join(","),
    ),
  ].join("\r\n");
}
