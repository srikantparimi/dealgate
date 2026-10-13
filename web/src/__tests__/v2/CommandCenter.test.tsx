import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CommandCenterPage } from "../../pages/v2/CommandCenter";
import * as commandApi from "../../api/commandCenter";
import * as clientApi from "../../api/client";

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ user: { sub: "u1", name: "Avery Owner", groups: ["SystemAdmin"] } }),
}));

const overview: commandApi.CommandOverview = {
  scope: { period: "this_quarter", months: ["2026-10", "2026-11", "2026-12"], currency: "USD", focus: "leadership" },
  actions: [{ id: "11111111-1111-1111-1111-111111111111", rank: 1, category: "Overdue action", account: "Acme", title: "Expansion", detail: "Review terms", owner: "Avery Owner", due: "2026-10-10", href: "/deals/11111111-1111-1111-1111-111111111111", action: "Open record" }],
  metrics: { open_opportunity_value: "500000", sows_in_progress: 2, committed_revenue: "120000", committed_gm_pct: null, planned_people: 4 },
  lifecycle: { pipeline: 1, intake: 1, scope_gm: 0, function_reviews: 1, ceo_exception: 0, signature: 0, handoff: 0, active: 1 },
  revenue: { actual: "20000", remaining_signed: "100000", potential_expected: "250000", potential_upside: "500000", currency: "USD", cost_coverage_complete: false, financial_blockers: ["rate missing"], months: [
    { month: "2026-10", actual: "20000", remaining_signed: "30000", potential_expected: "0", potential_upside: "0" },
    { month: "2026-11", actual: "0", remaining_signed: "35000", potential_expected: "100000", potential_upside: "200000" },
    { month: "2026-12", actual: "0", remaining_signed: "35000", potential_expected: "150000", potential_upside: "300000" },
  ] },
  capacity: { required_fte: null, allocated_fte: null, gap_fte: null, status: "unknown", message: "Workforce supply is not current.", gaps: [], source_status: "unknown", source_as_of: null, source_detail: "No current workforce source" },
  recent_changes: [],
  sources: [{ name: "HubSpot pipeline mirror", status: "current", as_of: "2026-10-13T12:00:00Z", detail: "3 deals" }],
  configuration_gaps: [],
};

const accounts: commandApi.CommandAccountsPage = {
  total: 1,
  page: 1,
  page_size: 25,
  scope_label: "HubSpot deals · Stage 5 and above",
  configuration_gaps: [],
  items: [{
    opportunity_id: "11111111-1111-1111-1111-111111111111", hubspot_deal_id: "hs-1", account_id: "22222222-2222-2222-2222-222222222222", account_name: "Acme", engagement_id: null, engagement_name: "Expansion", business_unit: "ST21", pipeline_id: "opaque-pipe", stage_id: "opaque-stage", stage_label: "Proposal", stage_order: 40, is_closed_won: false, sow_stage: "Signature", currency: "USD", deal_value: "500000", owner_id: "33333333-3333-3333-3333-333333333333", owner_name: "Avery Owner", owner_email: "avery@example.test", next_action: "Review terms", next_action_due: "2026-10-10", period_revenue: null, forecast_gm_pct: null, assigned_fte: "4", required_fte: null, financial_status: "incomplete", financial_blockers: ["rate missing"],
  }],
};

beforeEach(() => {
  vi.spyOn(commandApi, "getCommandOverview").mockResolvedValue(overview);
  vi.spyOn(commandApi, "getCommandAccounts").mockResolvedValue(accounts);
  vi.spyOn(commandApi, "downloadCommandAccounts").mockResolvedValue();
  vi.spyOn(clientApi, "getPipelineFacets").mockResolvedValue({ owners: [], business_units: ["ST21"] });
});

function renderPage(path = "/command") {
  return render(<MemoryRouter initialEntries={[path]}><CommandCenterPage /></MemoryRouter>);
}

describe("Command Center redesign", () => {
  it("renders real operational sections and keeps missing finance unknown", async () => {
    renderPage();
    expect(await screen.findByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("From opportunity to delivery")).toBeInTheDocument();
    expect(await screen.findByText("Acme", { selector: "button" })).toBeInTheDocument();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
    expect(screen.getByTestId("stage5-scope")).toHaveTextContent("HubSpot deals · Stage 5 and above");
    expect(screen.getByText("Open late-stage work, current-period wins and active delivery.")).toBeVisible();
  });

  it("reset removes user filters but preserves the mandatory Stage 5 scope", async () => {
    const user = userEvent.setup();
    renderPage("/command?bu=ST21&period=next_two_quarters");
    expect(await screen.findByRole("button", { name: "ST21" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset user filters" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "ST21" })).not.toBeInTheDocument());
    expect(screen.getByTestId("stage5-scope")).toBeInTheDocument();
  });

  it("opens an in-place account detail with real record destinations", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByText("Acme", { selector: "button" }));
    expect(screen.getByRole("dialog", { name: "Acme" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open deal" })).toHaveAttribute("href", "/deals/11111111-1111-1111-1111-111111111111");
    expect(screen.getByText("rate missing")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Acme" })).not.toBeInTheDocument();
  });

  it("keeps the Stage 5 account table available when the overview source fails", async () => {
    vi.mocked(commandApi.getCommandOverview).mockRejectedValueOnce(new Error("forecast unavailable"));
    renderPage();
    expect(await screen.findByText("Could not load actions: forecast unavailable")).toBeInTheDocument();
    expect(await screen.findByText("Acme", { selector: "button" })).toBeInTheDocument();
    expect(screen.getByTestId("stage5-scope")).toBeVisible();
  });

  it("keeps healthy overview sections available when the Stage 5 table fails", async () => {
    vi.mocked(commandApi.getCommandAccounts).mockRejectedValueOnce(new Error("pipeline unavailable"));
    renderPage();
    expect(await screen.findByText("Could not load accounts: pipeline unavailable")).toBeInTheDocument();
    expect(await screen.findByText("$120,000")).toBeInTheDocument();
    expect(screen.getByText("Protect delivery. Unlock growth.")).toBeVisible();
  });
});
