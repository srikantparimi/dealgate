// S23-PL2 L3 test data · workspace answers shaped like build-plan-api.md §2.6,
// with the prototype's numbers: "tonight" (staging, work columns empty) and
// "populated" (next actions, SOW states, agreements, watches). Plus router
// helpers to read the URL and press the browser's back button.
import { configure, render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import type { DealRow, StageCount, Workspace, WorkspaceQuery } from "../../api/pipelineWorkspace";
import { Toaster } from "../../ui-v2/primitives/toaster";

// The page mounts many Radix parts; under a full parallel run the first answer can take over a second.
configure({ asyncUtilTimeout: 5_000 });

export const TODAY = "2026-10-14";

export const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString();

const STAGES: [number, string, string, number, string, number][] = [
  [1, "Prospecting", "1 · Initial Contact / Prospecting", 22, "3950000", 0],
  [2, "Qualification", "2 · Qualification", 20, "4050000", 0],
  [3, "Fit gap analysis", "3 · Requirement / Fit Gap Analysis", 18, "3610000", 0],
  [4, "Proposal", "4 · Proposal", 19, "3058944.14", 0],
  [5, "Negotiation", "5 · Negotiation", 15, "3630000", 0],
  [6, "Contracting", "6 · Contracting / Drive Commitment", 13, "2960000", 0],
  [7, "Closed won", "7 · Closed Won", 14, "4340000", 0],
  [8, "Closed lost", "8 · Closed Lost", 9, "2730000", 0],
  [9, "On hold", "Hold (open, paused)", 2, "344500", 0],
];

export function stages(): StageCount[] {
  return STAGES.map(([stage_id, label, full_label, deals, known_value_usd, deals_without_amount]) => ({
    stage_id,
    label,
    full_label,
    deals,
    known_value_usd,
    deals_without_amount,
  }));
}

export const SOW_STATES = [
  { value: "none", label: "No SOW" },
  { value: "draft", label: "Draft" },
  { value: "in_review_delivery_hr", label: "In review · delivery/hr" },
  { value: "in_review_finance_legal", label: "In review · finance/legal" },
  { value: "changes_requested", label: "Changes requested" },
  { value: "ceo_exception", label: "CEO exception" },
  { value: "approved", label: "Approved" },
  { value: "awaiting_signature", label: "Awaiting signature" },
  { value: "signed", label: "Signed" },
];

export const OWNERS = [
  { id: "owner-sp", name: "Srikanth Parimi" },
  { id: "owner-jk", name: "Janice Krpan" },
  { id: "owner-sd", name: "Shawnna DelHierro" },
  { id: "owner-mh", name: "Michael Holman" },
];

/** Staging tonight: work columns empty, no agreement files anywhere. */
export function tonight(overrides: Partial<Workspace> = {}): Workspace {
  return {
    freshness: {
      state: "fresh",
      last_success_at: hoursAgo(7),
      last_attempt_at: hoursAgo(7),
      last_status: "ok",
      schedule: "nightly",
      deals_seen: 132,
      deals_written: 132,
      error_count: 0,
      errors: [],
      recovery: { available: true, admin_only: true },
    },
    metrics: {
      open_deals: { value: 109, accounts: 55, drill: { tab: "deals", status: "open" } },
      open_value_usd: { value: "21596444.14", includes_on_hold: 2, deals: 109, drill: { tab: "deals", status: "open" } },
      closing_this_month: {
        value: 15,
        value_usd: "2680000",
        drill: { tab: "deals", status: "open", date_field: "close", date_preset: "month" },
      },
      overdue_next_actions: { value: 0, with_next_action: 0, drill: { tab: "deals", attention: "overdue" } },
      pending_approvals: { value: 0, drill: { tab: "deals", sow: "pending" } },
      agreement_gap_clients: {
        value: 55,
        clients_total: 55,
        any_agreement_files: false,
        drill: { tab: "clients", missing: "agreements", include_unmatched_clients: false },
      },
    },
    stages: stages(),
    focus: { all_open: 109, closing_this_month: 15, mine: 33, mine_available: true, needs_attention: 26, watching: 0 },
    unmapped_regions: 0,
    rows: [],
    rows_by_stage: null,
    page: { number: 1, size: 25, total_rows: 109, total_value_usd: "21596444.14" },
    tab_counts: { deals: 109, clients: 55 },
    options: {
      deal_owners: OWNERS,
      account_owners: OWNERS,
      business_units: [
        { business_unit: "ST21", regions: ["US"] },
        { business_unit: "IT Avalon", regions: ["US"] },
        { business_unit: "Retro Rabbit", regions: ["South Africa"] },
      ],
      sow_states: SOW_STATES,
    },
    today: TODAY,
    ...overrides,
  };
}

/** The prototype's "Populated example". */
export function populated(overrides: Partial<Workspace> = {}): Workspace {
  const base = tonight();
  return {
    ...base,
    metrics: {
      ...base.metrics,
      overdue_next_actions: { value: 10, with_next_action: 37, drill: { tab: "deals", attention: "overdue" } },
      pending_approvals: { value: 11, drill: { tab: "deals", sow: "pending" } },
      agreement_gap_clients: {
        value: 33,
        clients_total: 55,
        any_agreement_files: true,
        drill: { tab: "clients", missing: "agreements", include_unmatched_clients: false },
      },
    },
    focus: { ...base.focus, needs_attention: 36, watching: 5 },
    ...overrides,
  };
}

/** The status the API sends with a row, for fixtures that only set a stage label. */
function statusFor(label: string): DealRow["status"] {
  const l = label.trim().toLowerCase();
  if (l.startsWith("closed won")) return "won";
  if (l.startsWith("closed lost")) return "lost";
  if (l === "on hold" || l === "hold") return "hold";
  return "open";
}

export function fakeDeal(overrides: Partial<DealRow> = {}): DealRow {
  const row: Omit<DealRow, "status"> = {
    id: "deal-1",
    title: "Cloud modernization",
    client: { id: "client-1", name: "Vector Systems" },
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

/** A workspace answer whose list total follows the query, so "card = list" can be checked. */
export function answerFor(query: Partial<WorkspaceQuery>, base: Workspace = populated()): Workspace {
  const m = base.metrics;
  let total = base.page.total_rows;
  if (query.tab === "clients" && query.missing === "agreements") total = m.agreement_gap_clients.value;
  else if (query.attention === "overdue") total = m.overdue_next_actions.value;
  else if (query.sow === "pending") total = m.pending_approvals.value;
  else if (query.date_preset === "month") total = m.closing_this_month.value;
  return { ...base, page: { ...base.page, total_rows: total } };
}

export function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

export function BackButton() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(-1)}>
      test: browser back
    </button>
  );
}

/** Renders the page at `url` inside the app's toaster and a router, with the URL probe and a back button. */
export function renderAt(page: ReactElement, url = "/pipeline") {
  return render(
    <Toaster>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route
            path="/pipeline"
            element={
              <>
                {page}
                <LocationProbe />
                <BackButton />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </Toaster>,
  );
}

/** The URL query the page is on, as URLSearchParams. */
export function currentParams(getByTestId: (id: string) => HTMLElement): URLSearchParams {
  return new URLSearchParams(getByTestId("location").textContent ?? "");
}
