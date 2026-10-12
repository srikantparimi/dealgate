/**
 * S22 · Portfolio & Forecast API client — docs/reference/openapi-forecast.yaml.
 *
 * Every number on these screens comes from the server (the forecast engine).
 * This module only types the wire shapes and issues requests; it never
 * computes a value (CLAUDE.md rule 9: no business math in the browser).
 */

import { request } from "./client";

export type UUID = string;
export type ISODate = string;
export type Money = string; // "339684.00"
export type Pct = number | null; // 0.3603 = 36.03 %

export type EngagementType = "fixed_cost" | "assessment" | "msp" | "time_and_materials" | "staff_augmentation";
export type EmploymentType = "w2_employee" | "contractor_1099";
export type Seniority = "Junior" | "Mid" | "Senior" | "Principal";
export type EngagementStatus = "draft" | "active" | "ended";
export type ForecastStatus = "PASS" | "BELOW FLOOR" | "INCOMPLETE";

export const ENGAGEMENT_TYPE_LABEL: Record<EngagementType, string> = {
  fixed_cost: "Fixed cost",
  assessment: "Assessment",
  msp: "MSP",
  time_and_materials: "Time & materials",
  staff_augmentation: "Staff augmentation",
};
export const EMPLOYMENT_TYPE_LABEL: Record<EmploymentType, string> = {
  w2_employee: "W-2 / Employee",
  contractor_1099: "1099 / Contractor",
};
export const SENIORITIES: Seniority[] = ["Junior", "Mid", "Senior", "Principal"];
export const HOURLY_TYPES: ReadonlySet<EngagementType> = new Set(["time_and_materials", "staff_augmentation"]);
export const FIXED_TYPES: ReadonlySet<EngagementType> = new Set(["fixed_cost", "assessment"]);
export const CURRENCIES = ["USD", "INR", "GBP", "EUR", "CAD"];

export interface EngagementIn {
  client_id: UUID;
  hubspot_deal_id?: string | null;
  opportunity_id?: UUID | null;
  name: string;
  type: EngagementType;
  start: ISODate;
  end: ISODate;
  total_price?: string | null;
  monthly_fee?: string | null;
  currency?: string;
  additional_costs_flag: boolean;
  same_dates_for_all: boolean;
  owner_user_id?: UUID | null;
}

export interface Engagement {
  id: UUID;
  client_id: UUID;
  client_name: string;
  hubspot_deal_id: string | null;
  opportunity_id: UUID | null;
  name: string;
  type: EngagementType;
  start: ISODate;
  end: ISODate;
  total_price: Money | null;
  monthly_fee: Money | null;
  currency: string;
  additional_costs_flag: boolean;
  same_dates_for_all: boolean;
  owner_user_id: UUID | null;
  owner_name: string | null;
  status: EngagementStatus;
  duration_months: number;
}

export interface EngagementListResponse {
  total: number;
  page: number;
  page_size: number;
  items: Engagement[];
}

export interface AllocationIn {
  resource_id: UUID;
  role?: string | null;
  seniority?: Seniority | null;
  location?: string | null;
  employment_type?: EmploymentType | null;
  assignment?: string | null;
  utilization?: number | string;
  bill_rate?: string | null;
  cost_per_hour?: string | null;
  start?: ISODate | null;
  end?: ISODate | null;
  hours_override?: string | null;
}

export type AllocationPatch = Partial<Omit<AllocationIn, "resource_id">>;

export interface AllocationTotals {
  working_days: number;
  hours: number;
  revenue: Money;
  /** Absent for callers without cost access (blueprint §3). */
  loaded_cost?: Money;
  row_gm_pct?: Pct;
  under_resource_floor?: boolean;
}

export interface Allocation {
  id: UUID;
  engagement_id: UUID;
  resource_id: UUID;
  resource_name: string;
  role: string;
  seniority: Seniority | null;
  location: string;
  employment_type: EmploymentType;
  assignment: string | null;
  utilization: number;
  bill_rate: Money | null;
  /** Absent for callers without cost access. */
  cost_per_hour?: Money | null;
  cost_per_hour_effective?: Money | null;
  burden_pct?: Pct;
  start: ISODate | null;
  end: ISODate | null;
  effective_start: ISODate;
  effective_end: ISODate;
  hours_override: number | null;
  superseded_by: UUID | null;
  totals: AllocationTotals;
}

export interface EngagementCostIn {
  description: string;
  category?: string | null;
  location?: string | null;
  amount: string;
  frequency: "one_time" | "monthly";
  billed_to_client: boolean;
}

export interface EngagementCost extends EngagementCostIn {
  id: UUID;
  engagement_id: UUID;
  amount: Money;
}

export interface MonthLine {
  month: string;
  share_of_month: number;
  people: number;
  hours: number;
  revenue: Money;
  labour_cost: Money;
  burden_cost: Money;
  loaded_cost: Money;
  additional_costs: Money;
  pass_through_revenue: Money;
  total_revenue: Money;
  total_cost: Money;
  gm: Money;
  gm_pct: Pct;
}

export interface AssignmentLine {
  people: number;
  hours: number;
  revenue: Money;
  loaded_cost?: Money;
  gm_pct?: Pct;
}

export interface AllocationMonth {
  allocation_id: UUID;
  resource_name: string;
  assignment: string;
  month: string;
  working_days: number;
  hours: number;
  revenue: Money;
  loaded_cost?: Money;
}

export interface LocationCheck {
  revenue: Money;
  loaded_cost: Money;
  gm_pct: Pct;
  floor: Pct;
  ok: boolean;
}

export interface Forecast {
  engagement_id: UUID;
  duration_months: number;
  status: ForecastStatus;
  project_floor_pct: Pct;
  monthly_required: boolean;
  missing: string[];
  totals: {
    hours: number;
    labour_cost: Money;
    burden_cost: Money;
    loaded_cost: Money;
    additional_costs: Money;
    pass_through_revenue: Money;
    total_revenue: Money;
    total_cost: Money;
    gm: Money;
    gm_pct: Pct;
  };
  /** Allocations-grid footer: sums of the engine's allocation-month rows. Cost keys absent without cost access. */
  staffing_totals?: { hours: number; revenue: Money; loaded_cost?: Money; gm_pct?: Pct };
  months: MonthLine[];
  by_assignment: Record<string, Record<string, AssignmentLine>>;
  by_assignment_totals?: Record<string, { people: number; hours: number; revenue: Money; loaded_cost?: Money; gm_pct?: Pct }>;
  allocation_months: AllocationMonth[];
  location_check: Record<string, LocationCheck>;
}

export interface PortfolioRow {
  engagement_id: UUID;
  client_name: string;
  name: string;
  type: EngagementType;
  start: ISODate;
  end: ISODate;
  people: number;
  revenue_month: Money;
  cost_month: Money;
  gm_pct_month: Pct;
  gm_pct_term: Pct;
  status: ForecastStatus;
}

export interface Rolloff {
  engagement_id: UUID;
  allocation_id: UUID;
  client: string;
  resource: string;
  role: string;
  assignment: string | null;
  end: ISODate;
}

export interface BenchRow {
  resource_id: UUID;
  resource: string;
  location: string;
  employment_type: EmploymentType;
  seniority: Seniority | null;
  free_from: ISODate;
}

export interface PortfolioForecast {
  month: string;
  project_floor_pct: Pct;
  cards: { portfolio_gm_pct: Pct; below_floor: number; rolloffs_60d: number; bench: number };
  rows: PortfolioRow[];
  totals: { people: number; revenue: Money; cost: Money; gm_pct: Pct };
  rolloffs: Rolloff[];
  bench_list: BenchRow[];
}

export interface ClientOption {
  id: UUID;
  name: string;
  source: "hubspot" | "manual";
}

export interface Resource {
  id: UUID;
  name: string;
  location: string;
  employment_type: EmploymentType;
  seniority: Seniority | null;
  email: string | null;
  active: boolean;
}

export interface ResourceIn {
  name: string;
  location: string;
  employment_type: EmploymentType;
  seniority?: Seniority | null;
  email?: string | null;
}

export interface CalendarLocation {
  name: string;
  burden_pct_w2: number;
  burden_pct_1099: number;
  resource_floor_pct: number;
}

export interface RateCardCell {
  seniority: Seniority;
  location: string;
  employment_type: EmploymentType;
  cost_per_hour: Money;
}

export interface ForecastCalendar {
  hours_per_day: number;
  project_floor_pct: number;
  locations: CalendarLocation[];
  rate_card: RateCardCell[];
  holidays: Record<string, ISODate[]>;
}

export interface PortfolioFilters {
  month: string;
  type?: EngagementType | "";
  client_id?: UUID | "";
}

function query(params: object): string {
  const p = new URLSearchParams();
  for (const [key, value] of Object.entries(params as Record<string, string | number | undefined | null>)) {
    if (value !== undefined && value !== null && value !== "") p.set(key, String(value));
  }
  const text = p.toString();
  return text ? `?${text}` : "";
}

// ---- engagements -------------------------------------------------------------

export function listEngagements(params: {
  client_id?: UUID;
  type?: EngagementType;
  status?: EngagementStatus;
  page?: number;
  page_size?: 25 | 50 | 100;
} = {}): Promise<EngagementListResponse> {
  return request<EngagementListResponse>(`/engagements${query(params)}`);
}

export function createEngagement(body: EngagementIn): Promise<Engagement> {
  return request<Engagement>("/engagements", { method: "POST", body: JSON.stringify(body) });
}

export function getEngagement(id: UUID): Promise<Engagement> {
  return request<Engagement>(`/engagements/${id}`);
}

export function patchEngagement(id: UUID, body: Partial<EngagementIn>): Promise<Engagement> {
  return request<Engagement>(`/engagements/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function getEngagementForecast(id: UUID): Promise<Forecast> {
  return request<Forecast>(`/engagements/${id}/forecast`);
}

// ---- allocations -------------------------------------------------------------

export function listAllocations(engagementId: UUID): Promise<Allocation[]> {
  return request<Allocation[]>(`/engagements/${engagementId}/allocations`);
}

export function addAllocation(engagementId: UUID, body: AllocationIn): Promise<Allocation> {
  return request<Allocation>(`/engagements/${engagementId}/allocations`, { method: "POST", body: JSON.stringify(body) });
}

export function patchAllocation(id: UUID, body: AllocationPatch): Promise<Allocation> {
  return request<Allocation>(`/allocations/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function deleteAllocation(id: UUID): Promise<void> {
  return request<void>(`/allocations/${id}`, { method: "DELETE" });
}

export function closeAllocation(id: UUID, end?: ISODate | null): Promise<Allocation> {
  return request<Allocation>(`/allocations/${id}/close`, { method: "POST", body: JSON.stringify(end ? { end } : {}) });
}

export function rehireAllocation(
  id: UUID,
  body: { start?: ISODate | null; bill_rate?: string | null; cost_per_hour?: string | null } = {},
): Promise<Allocation> {
  return request<Allocation>(`/allocations/${id}/rehire`, { method: "POST", body: JSON.stringify(body) });
}

export interface HoursCheckRow {
  role: string;
  sheet_hours: number | null;
  engine_hours: number;
  note: string;
}

export interface WorkbookImportResult {
  engagement: Engagement;
  forecast: Forecast;
  warnings: string[];
  hours_check: HoursCheckRow[];
}

/** POST /engagements/import-workbook — the DealGate cost-margin sheet (.xlsx) becomes an engagement. */
export function importWorkbook(file: File): Promise<WorkbookImportResult> {
  const form = new FormData();
  form.set("file", file);
  return request<WorkbookImportResult>("/engagements/import-workbook", { method: "POST", body: form });
}

/** The 422 body of the workbook import: every problem in the sheet's own words. */
export function errorsFrom(error: unknown): string[] | null {
  if (error && typeof error === "object" && "body" in error) {
    const body = (error as { body: unknown }).body;
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (detail && typeof detail === "object" && Array.isArray((detail as { errors?: unknown }).errors)) {
        return (detail as { errors: string[] }).errors;
      }
    }
  }
  return null;
}

const IMPORT_NOTE_KEY = "dealgate.s22.import-note";

/** Remember an import's warnings + hours check for the engagement header to show once. */
export function rememberImportNote(engagementId: UUID, result: WorkbookImportResult): void {
  try {
    sessionStorage.setItem(`${IMPORT_NOTE_KEY}:${engagementId}`, JSON.stringify({ warnings: result.warnings, hours_check: result.hours_check }));
  } catch {
    /* storage unavailable: the note is simply not shown */
  }
}

export function takeImportNote(engagementId: UUID): { warnings: string[]; hours_check: HoursCheckRow[] } | null {
  try {
    const raw = sessionStorage.getItem(`${IMPORT_NOTE_KEY}:${engagementId}`);
    return raw ? (JSON.parse(raw) as { warnings: string[]; hours_check: HoursCheckRow[] }) : null;
  } catch {
    return null;
  }
}

export function dismissImportNote(engagementId: UUID): void {
  try {
    sessionStorage.removeItem(`${IMPORT_NOTE_KEY}:${engagementId}`);
  } catch {
    /* ignore */
  }
}

export function importAllocations(engagementId: UUID, file: File): Promise<{ created: number; allocation_ids: UUID[] }> {
  const form = new FormData();
  form.set("engagement_id", engagementId);
  form.set("file", file);
  return request<{ created: number; allocation_ids: UUID[] }>("/allocations/import", { method: "POST", body: form });
}

// ---- costs --------------------------------------------------------------------

export function listCosts(engagementId: UUID): Promise<EngagementCost[]> {
  return request<EngagementCost[]>(`/engagements/${engagementId}/costs`);
}

export function addCost(engagementId: UUID, body: EngagementCostIn): Promise<EngagementCost> {
  return request<EngagementCost>(`/engagements/${engagementId}/costs`, { method: "POST", body: JSON.stringify(body) });
}

export function patchCost(id: UUID, body: Partial<EngagementCostIn>): Promise<EngagementCost> {
  return request<EngagementCost>(`/costs/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function deleteCost(id: UUID): Promise<void> {
  return request<void>(`/costs/${id}`, { method: "DELETE" });
}

// ---- portfolio -----------------------------------------------------------------

export function getPortfolioForecast(filters: PortfolioFilters): Promise<PortfolioForecast> {
  return request<PortfolioForecast>(`/portfolio/forecast${query(filters)}`);
}

export function portfolioCsvPath(filters: PortfolioFilters): string {
  return `/portfolio/forecast.csv${query(filters)}`;
}

/** Fetches the server-rendered CSV with the caller's token and hands it to the browser as a download. */
export async function downloadPortfolioCsv(filters: PortfolioFilters): Promise<void> {
  const text = await request<string>(portfolioCsvPath(filters));
  const blob = new Blob([typeof text === "string" ? text : JSON.stringify(text)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `portfolio-forecast-${filters.month}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

// ---- clients + people -------------------------------------------------------------

export function listClientOptions(): Promise<ClientOption[]> {
  return request<ClientOption[]>("/portfolio/clients");
}

export function createClient(name: string): Promise<ClientOption> {
  return request<ClientOption>("/clients", { method: "POST", body: JSON.stringify({ name }) });
}

export function listResources(): Promise<Resource[]> {
  return request<Resource[]>("/resources");
}

export function createResource(body: ResourceIn): Promise<Resource> {
  return request<Resource>("/resources", { method: "POST", body: JSON.stringify(body) });
}

// ---- settings --------------------------------------------------------------------

export function getForecastSettings(): Promise<ForecastCalendar> {
  return request<ForecastCalendar>("/settings/forecast");
}

export function putForecastSettings(body: ForecastCalendar): Promise<ForecastCalendar> {
  return request<ForecastCalendar>("/settings/forecast", { method: "PUT", body: JSON.stringify(body) });
}

/** The 422 body the API returns: every problem in the user's words (the engine's strings). */
export function missingFrom(error: unknown): string[] | null {
  if (error && typeof error === "object" && "body" in error) {
    const body = (error as { body: unknown }).body;
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (detail && typeof detail === "object" && Array.isArray((detail as { missing?: unknown }).missing)) {
        return (detail as { missing: string[] }).missing;
      }
    }
  }
  return null;
}
