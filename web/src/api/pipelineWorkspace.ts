// S23-PL2 · the Pipeline workspace (docs/reference/openapi-pipeline.yaml).
// One request per view carries freshness, metrics, stage counts, focus counts
// and the rows of the active tab. Money arrives as decimal strings summed on
// the server (CLAUDE.md rule 2); the browser formats it and never adds it up.
import {
  request,
  requestBlob,
  type DecimalStr,
  type ISODate,
  type ISODateTime,
  type UUID,
} from "./client";

export type WorkspaceTab = "deals" | "clients";
export type WorkspaceStatus = "open" | "all" | "won" | "lost" | "hold";
export type BusinessUnit = "ST21" | "IT Avalon" | "Retro Rabbit";
export type BusinessUnitFilter = BusinessUnit | "unmapped";
export type AttentionFilter =
  | "overdue"
  | "past_close"
  | "no_owner"
  | "inactive"
  | "pending_approval"
  | "any";
export type MissingFilter = "owner" | "close" | "activity" | "next_action" | "nda" | "msa" | "agreements";
export type DateField = "close" | "created" | "activity";
export type DatePreset =
  | "any"
  | "passed"
  | "next7"
  | "next30"
  | "next90"
  | "last7"
  | "last30"
  | "last90"
  | "month"
  | "quarter"
  | "custom";
export type WorkspaceSort = "value" | "close" | "activity" | "name";
export type WorkspaceLayout = "list" | "board";
export type WorkspacePageSize = 25 | 50 | 100;
export const WORKSPACE_PAGE_SIZES: readonly WorkspacePageSize[] = [25, 50, 100];

/** Every workspace parameter, as the API takes it. A saved view stores tab, layout and the rest as `filters`. */
export interface WorkspaceQuery {
  tab: WorkspaceTab;
  status: WorkspaceStatus;
  stage: number[];
  owner: string[];
  account_owner: string[];
  bu: BusinessUnitFilter[];
  q: string;
  sow: string | null;
  attention: AttentionFilter | null;
  missing: MissingFilter | null;
  group: UUID | null;
  watching: boolean;
  mine: boolean;
  date_field: DateField;
  date_preset: DatePreset;
  date_from: ISODate | null;
  date_to: ISODate | null;
  include_unmatched_clients: boolean;
  sort: WorkspaceSort;
  layout: WorkspaceLayout;
  page: number;
  page_size: WorkspacePageSize;
  /** Additive (not in the contract): one client's deals, for the client preview. */
  client?: UUID | null;
}

export const DEFAULT_WORKSPACE_QUERY: WorkspaceQuery = {
  tab: "deals",
  status: "open",
  stage: [],
  owner: [],
  account_owner: [],
  bu: [],
  q: "",
  sow: null,
  attention: null,
  missing: null,
  group: null,
  watching: false,
  mine: false,
  date_field: "close",
  date_preset: "any",
  date_from: null,
  date_to: null,
  include_unmatched_clients: false,
  sort: "value",
  layout: "list",
  page: 1,
  page_size: 25,
  client: null,
};

export interface Freshness {
  state: "fresh" | "stale" | "failed";
  last_success_at: ISODateTime | null;
  last_attempt_at: ISODateTime | null;
  last_status: "ok" | "partial" | "failed";
  schedule: string;
  deals_seen?: number;
  deals_written?: number;
  error_count?: number;
  errors?: { hubspot_id: string; reason: string }[];
  recovery?: { available: boolean; admin_only: boolean };
}

/** Query parameters to merge into the current filters; the list they open has the metric's length. */
export type MetricDrill = Partial<WorkspaceQuery>;

export interface WorkspaceMetrics {
  open_deals: { value: number; accounts: number; drill: MetricDrill };
  open_value_usd: { value: DecimalStr; includes_on_hold: number; deals: number; drill: MetricDrill };
  closing_this_month: { value: number; value_usd: DecimalStr; drill: MetricDrill };
  overdue_next_actions: { value: number; with_next_action: number; drill: MetricDrill };
  pending_approvals: { value: number; drill: MetricDrill };
  agreement_gap_clients: {
    value: number;
    clients_total: number;
    any_agreement_files: boolean;
    drill: MetricDrill;
  };
}

export interface StageCount {
  stage_id: number;
  label: string;
  full_label: string;
  deals: number;
  known_value_usd: DecimalStr;
  deals_without_amount: number;
}

export interface FocusCounts {
  all_open: number;
  closing_this_month: number;
  mine: number | null;
  mine_available: boolean;
  needs_attention: number;
  watching: number;
}

export type OwnerState = "active" | "archived" | "none";
export interface Owner {
  name: string | null;
  state: OwnerState;
}

export interface Agreements {
  nda_on_file: boolean;
  msa_on_file: boolean;
}

export type DealFlag = "action_overdue" | "close_passed" | "no_owner" | "inactive_14d";
export type ClientFlag = "no_owner" | "action_overdue" | "close_passed";

export interface DealRow {
  id: UUID;
  title: string;
  /** Both null for a deal with no client (none on staging; shown as "No client"). */
  client: { id: UUID | null; name: string | null };
  /** Null when the deal's stage is not in the live stage mirror. */
  stage_id: number | null;
  stage_label: string;
  /** Additive: open (Hold reads "hold"; Hold counts as open), won or lost. */
  status: "open" | "hold" | "won" | "lost";
  amount: DecimalStr | null;
  /** Null when HubSpot sent no currency; the API then leaves the amount out of every USD total. */
  currency: string | null;
  business_unit: BusinessUnit | null;
  region: string | null;
  region_note: string | null;
  hubspot_region: string | null;
  bu_unmapped: boolean;
  deal_owner: Owner;
  account_owner: Owner;
  close_date: ISODate | null;
  created_date: ISODate | null;
  last_activity_date: ISODate | null;
  days_since_activity: number | null;
  sow_state: string;
  sow_state_label: string;
  sow_count: number;
  agreements: Agreements;
  next_action: { id: UUID; text: string; due_on: ISODate | null } | null;
  flags: DealFlag[];
  watching: boolean;
  /** Only for building the "HubSpot ↗" link; never shown. */
  hubspot_deal_id: string | null;
  pipeline_label: string | null;
}

export interface ClientRow {
  id: UUID;
  name: string;
  account_owner: Owner;
  matching_deals: number;
  open_deals: number;
  matching_value_usd: DecimalStr | null;
  earliest_close_date: ISODate | null;
  last_activity_date: ISODate | null;
  days_since_activity: number | null;
  agreements: Agreements;
  flags: ClientFlag[];
  /** Only for building a HubSpot link; never shown. */
  hubspot_company_id: string | null;
}

export interface BoardLane {
  total: number;
  value_usd: DecimalStr;
  deals: DealRow[];
}

export interface WorkspaceOptions {
  deal_owners: { id: string; name: string }[];
  account_owners: { id: string; name: string }[];
  business_units: { business_unit: BusinessUnit; regions: string[] }[];
  sow_states: { value: string; label: string }[];
}

export interface Workspace {
  freshness: Freshness;
  metrics: WorkspaceMetrics;
  stages: StageCount[];
  focus: FocusCounts;
  unmapped_regions: number;
  rows: DealRow[] | ClientRow[];
  rows_by_stage: Record<string, BoardLane> | null;
  page: { number: number; size: number; total_rows: number; total_value_usd: DecimalStr | null };
  tab_counts: { deals: number; clients: number };
  options: WorkspaceOptions;
  /** The calendar date in America/Los_Angeles the numbers were computed for. */
  today: ISODate;
}

/** The query string for a workspace or export request. Defaults are left out. */
export function workspaceParams(
  query: Partial<WorkspaceQuery>,
  opts: { forExport?: boolean } = {},
): URLSearchParams {
  const q = { ...DEFAULT_WORKSPACE_QUERY, ...query };
  const d = DEFAULT_WORKSPACE_QUERY;
  const p = new URLSearchParams();
  if (q.tab !== d.tab) p.set("tab", q.tab);
  // Always sent: the API's default is "open", and a link must say what it shows.
  p.set("status", q.status);
  q.stage.forEach((s) => p.append("stage", String(s)));
  q.owner.forEach((o) => p.append("owner", o));
  q.account_owner.forEach((o) => p.append("account_owner", o));
  q.bu.forEach((b) => p.append("bu", b));
  if (q.q.trim()) p.set("q", q.q.trim());
  if (q.sow) p.set("sow", q.sow);
  if (q.attention) p.set("attention", q.attention);
  if (q.missing) p.set("missing", q.missing);
  if (q.group) p.set("group", q.group);
  if (q.watching) p.set("watching", "true");
  if (q.mine) p.set("mine", "true");
  if (q.date_preset !== "any") {
    p.set("date_field", q.date_field);
    p.set("date_preset", q.date_preset);
    if (q.date_preset === "custom") {
      if (q.date_from) p.set("date_from", q.date_from);
      if (q.date_to) p.set("date_to", q.date_to);
    }
  }
  if (q.include_unmatched_clients) p.set("include_unmatched_clients", "true");
  if (q.sort !== d.sort) p.set("sort", q.sort);
  if (q.client) p.set("client", q.client);
  if (!opts.forExport) {
    if (q.layout !== d.layout) p.set("layout", q.layout);
    if (q.page !== d.page) p.set("page", String(q.page));
    if (q.page_size !== d.page_size) p.set("page_size", String(q.page_size));
  }
  return p;
}

export function getWorkspace(query: Partial<WorkspaceQuery>, signal?: AbortSignal): Promise<Workspace> {
  return request<Workspace>(`/pipeline/workspace?${workspaceParams(query)}`, { signal });
}

/** Every filtered row of the active tab as CSV (UTF-8 with BOM), saved through the browser. */
export async function downloadWorkspaceCsv(query: Partial<WorkspaceQuery>): Promise<string> {
  const { blob, filename } = await requestBlob(
    `/pipeline/export?${workspaceParams(query, { forExport: true })}`,
  );
  const name = filename ?? `DealGate_Pipeline_${query.tab ?? "deals"}.csv`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return name;
}

// --- personal workspace ------------------------------------------------------

export interface SavedWorkspaceView {
  id: UUID;
  name: string;
  tab: WorkspaceTab;
  layout: WorkspaceLayout;
  filters: Partial<WorkspaceQuery>;
}

export interface TrackingGroupSummary {
  id: UUID;
  name: string;
  deal_ids: UUID[];
}

export function listWorkspaceViews(): Promise<SavedWorkspaceView[]> {
  return request<SavedWorkspaceView[]>(`/pipeline/views`);
}

export function createWorkspaceView(body: Omit<SavedWorkspaceView, "id">): Promise<SavedWorkspaceView> {
  return request<SavedWorkspaceView>(`/pipeline/views`, { method: "POST", body: JSON.stringify(body) });
}

export function deleteWorkspaceView(id: UUID): Promise<void> {
  return request<void>(`/pipeline/views/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function listWorkspaceGroups(): Promise<TrackingGroupSummary[]> {
  return request<TrackingGroupSummary[]>(`/pipeline/groups`);
}

export function createWorkspaceGroup(body: { name: string; deal_ids?: UUID[] }): Promise<TrackingGroupSummary> {
  return request<TrackingGroupSummary>(`/pipeline/groups`, { method: "POST", body: JSON.stringify(body) });
}

export function addDealsToGroup(groupId: UUID, dealIds: UUID[]): Promise<void> {
  return request<void>(`/pipeline/groups/${encodeURIComponent(groupId)}/deals`, {
    method: "PUT",
    body: JSON.stringify({ deal_ids: dealIds }),
  });
}

export function removeDealsFromGroup(groupId: UUID, dealIds: UUID[]): Promise<void> {
  // Ids also go in the query string: proxies may drop a DELETE body.
  const p = new URLSearchParams();
  dealIds.forEach((id) => p.append("deal_ids", id));
  return request<void>(`/pipeline/groups/${encodeURIComponent(groupId)}/deals?${p}`, {
    method: "DELETE",
    body: JSON.stringify({ deal_ids: dealIds }),
  });
}

export function watchDeal(dealId: UUID): Promise<void> {
  return request<void>(`/pipeline/watching/${encodeURIComponent(dealId)}`, { method: "PUT" });
}

export function unwatchDeal(dealId: UUID): Promise<void> {
  return request<void>(`/pipeline/watching/${encodeURIComponent(dealId)}`, { method: "DELETE" });
}
