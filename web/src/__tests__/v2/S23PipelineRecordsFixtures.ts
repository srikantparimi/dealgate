// S23-PL2 L4 · shared test data for the Pipeline records tests (not a test file).
// "Tonight" rows look like staging tonight (D31: no SOW, no agreements, no next
// actions); "populated" rows carry every work column.
import {
  DEFAULT_WORKSPACE_QUERY,
  type ClientRow,
  type DealRow,
  type StageCount,
  type Workspace,
  type WorkspaceQuery,
} from "../../api/pipelineWorkspace";
import type { WorkspaceUrlState } from "../../pages/v2/pipeline/workspaceState";

export const TODAY = "2026-10-14";

export const STAGES: StageCount[] = [
  [1, "Prospecting", "1 · Initial Contact / Prospecting"],
  [2, "Qualification", "2 · Qualification"],
  [3, "Fit gap analysis", "3 · Requirement / Fit Gap Analysis"],
  [4, "Proposal", "4 · Proposal"],
  [5, "Negotiation", "5 · Negotiation"],
  [6, "Contracting", "6 · Contracting / Drive Commitment"],
  [7, "Closed won", "7 · Closed Won"],
  [8, "Closed lost", "8 · Closed Lost"],
  [9, "On hold", "Hold (open, paused)"],
].map(([stage_id, label, full_label]) => ({
  stage_id: stage_id as number,
  label: label as string,
  full_label: full_label as string,
  deals: 0,
  known_value_usd: "0",
  deals_without_amount: 0,
}));

export const SOW_STATES = [
  ["none", "No SOW"],
  ["draft", "Draft"],
  ["in_review_delivery_hr", "In review · delivery/hr"],
  ["in_review_finance_legal", "In review · finance/legal"],
  ["changes_requested", "Changes requested"],
  ["ceo_exception", "CEO exception"],
  ["approved", "Approved"],
  ["awaiting_signature", "Awaiting signature"],
  ["signed", "Signed"],
].map(([value, label]) => ({ value: value as string, label: label as string }));

let seq = 0;
const uuid = () => `00000000-0000-4000-8000-${String(++seq).padStart(12, "0")}`;

/** Tonight's first row: "Cloud modernization" / "Vector Systems", every work column empty. */
/** The status the API sends with a row, for fixtures that only set a stage label. */
function statusFor(label: string): DealRow["status"] {
  const l = label.trim().toLowerCase();
  if (l.startsWith("closed won")) return "won";
  if (l.startsWith("closed lost")) return "lost";
  if (l === "on hold" || l === "hold") return "hold";
  return "open";
}

export function deal(overrides: Partial<DealRow> = {}): DealRow {
  const row: Omit<DealRow, "status"> = {
    id: uuid(),
    title: "Cloud modernization",
    client: { id: "c0000000-0000-4000-8000-000000000001", name: "Vector Systems" },
    stage_id: 6,
    stage_label: "Contracting",
    amount: "542000",
    currency: "USD",
    business_unit: "IT Avalon",
    region: "US",
    region_note: null,
    hubspot_region: "US - IT Avalon",
    bu_unmapped: false,
    deal_owner: { name: "Srikanth Parimi", state: "active" },
    account_owner: { name: null, state: "none" },
    close_date: "2026-12-28",
    created_date: "2026-09-12",
    last_activity_date: null,
    days_since_activity: null,
    sow_state: "none",
    sow_state_label: "No SOW",
    sow_count: 0,
    agreements: { nda_on_file: false, msa_on_file: false },
    next_action: null,
    flags: [],
    watching: false,
    hubspot_deal_id: "9001",
    pipeline_label: "Global sales pipeline",
    ...overrides,
  };
  return { ...row, status: overrides.status ?? statusFor(row.stage_label) };
}

/** Populated: overdue next action, IT Avalon · US · Staffing, a date in next year. */
export function overdueDeal(overrides: Partial<DealRow> = {}): DealRow {
  return deal({
    title: "Quality engineering pod",
    client: { id: "c0000000-0000-4000-8000-000000000002", name: "Keystone Energy" },
    stage_id: 3,
    stage_label: "Fit gap analysis",
    amount: "420000",
    region_note: "Staffing",
    hubspot_region: "US - IT Avalon (Staffing)",
    close_date: "2027-03-15",
    next_action: { id: "a0000000-0000-4000-8000-000000000001", text: "Confirm final commercial terms", due_on: "2026-10-13" },
    flags: ["action_overdue"],
    ...overrides,
  });
}

/** Populated: SOW in review (pending), NDA on file, 11 days since activity. */
export function reviewDeal(overrides: Partial<DealRow> = {}): DealRow {
  return deal({
    title: "Application support",
    client: { id: "c0000000-0000-4000-8000-000000000003", name: "Meridian Partners" },
    stage_id: 5,
    stage_label: "Negotiation",
    amount: "404000",
    deal_owner: { name: "Michael Holman", state: "active" },
    account_owner: { name: "Janice Krpan", state: "active" },
    close_date: "2026-12-10",
    last_activity_date: "2026-10-03",
    days_since_activity: 11,
    sow_state: "in_review_delivery_hr",
    sow_state_label: "In review · delivery/hr",
    sow_count: 1,
    agreements: { nda_on_file: true, msa_on_file: false },
    ...overrides,
  });
}

/** Closed won with an archived HubSpot owner. */
export function wonDeal(overrides: Partial<DealRow> = {}): DealRow {
  return deal({
    title: "Integration modernization",
    client: { id: "c0000000-0000-4000-8000-000000000004", name: "Keystone Mobility" },
    stage_id: 7,
    stage_label: "Closed won",
    amount: "519000",
    business_unit: "ST21",
    region: "US",
    hubspot_region: "US",
    deal_owner: { name: null, state: "archived" },
    close_date: "2026-10-02",
    last_activity_date: "2026-08-19",
    days_since_activity: 56,
    sow_state: "signed",
    sow_state_label: "Signed",
    sow_count: 1,
    agreements: { nda_on_file: true, msa_on_file: true },
    ...overrides,
  });
}

export function client(overrides: Partial<ClientRow> = {}): ClientRow {
  return {
    id: uuid(),
    name: "Bramble Bank",
    account_owner: { name: "Srikanth Parimi", state: "active" },
    matching_deals: 2,
    open_deals: 2,
    matching_value_usd: "665500",
    earliest_close_date: "2026-11-20",
    last_activity_date: "2026-10-08",
    days_since_activity: 6,
    agreements: { nda_on_file: true, msa_on_file: true },
    flags: [],
    hubspot_company_id: "77",
    ...overrides,
  };
}

export function workspace(overrides: Partial<Workspace> = {}): Workspace {
  const rows = overrides.rows ?? [];
  return {
    freshness: {
      state: "fresh",
      last_success_at: "2026-10-14T09:10:00Z",
      last_attempt_at: "2026-10-14T09:10:00Z",
      last_status: "ok",
      schedule: "nightly",
    },
    metrics: {
      open_deals: { value: 109, accounts: 55, drill: { tab: "deals", status: "open" } },
      open_value_usd: { value: "21596444.14", includes_on_hold: 2, deals: 109, drill: { tab: "deals", status: "open" } },
      closing_this_month: { value: 15, value_usd: "2680000", drill: { tab: "deals", status: "open" } },
      overdue_next_actions: { value: 0, with_next_action: 0, drill: { tab: "deals", attention: "overdue" } },
      pending_approvals: { value: 0, drill: { tab: "deals", sow: "pending" } },
      agreement_gap_clients: {
        value: 55,
        clients_total: 55,
        any_agreement_files: false,
        drill: { tab: "clients", missing: "agreements", include_unmatched_clients: false },
      },
    },
    stages: STAGES,
    focus: { all_open: 109, closing_this_month: 15, mine: 33, mine_available: true, needs_attention: 26, watching: 0 },
    unmapped_regions: 0,
    rows,
    rows_by_stage: null,
    page: { number: 1, size: 25, total_rows: rows.length, total_value_usd: "21596444.14" },
    tab_counts: { deals: 109, clients: 55 },
    options: { deal_owners: [], account_owners: [], business_units: [], sow_states: SOW_STATES },
    today: TODAY,
    ...overrides,
  };
}

export function urlState(query: Partial<WorkspaceQuery> = {}): WorkspaceUrlState {
  return { query: { ...DEFAULT_WORKSPACE_QUERY, ...query }, statusBefore: null };
}

/** The HTML and spreadsheet strings F15/T6 must show literally. */
export const INJECTION_TITLE = "<img src=x onerror=alert(1)>";
export const INJECTION_CLIENT = '=HYPERLINK("http://x","y")';
