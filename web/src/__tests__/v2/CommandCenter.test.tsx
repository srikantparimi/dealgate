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
  actions: [{ id: "11111111-1111-1111-1111-111111111111", rank: 1, category: "Closed-won without engagement", account: "Acme", title: "Expansion", detail: "Closed-won work has no linked delivery engagement.", owner: "Avery Owner", due: "2026-10-10", href: "/deals/11111111-1111-1111-1111-111111111111", action: "Create engagement from deal", impact: "500000", impact_label: "Contract value", period: "Closed-won deal", missing_input: null }],
  brief: [
    { kind: "risk", title: "Contract value: 500000.00", detail: "Acme · Closed-won work has no linked delivery engagement.", href: "/deals/11111111-1111-1111-1111-111111111111" },
    { kind: "opportunity", title: "250000.00 weighted pipeline across 1 eligible deal(s)", detail: "250000.00 is unscheduled and remains outside monthly revenue.", href: "/pipeline?status=open&sow=none" },
    { kind: "blocker", title: "1 record needs financial inputs", detail: "Applicable staffing cost rate", href: "/engagements/one" },
  ],
  tiles: {
    revenue: { forecast: "50000", actual_to_date: null, actual_cutoff: null, latest_actual_month: "2026-09", latest_actual: "20000", last_closed_billing_loss: null, comparison: { value: "5000", basis: "versus prior month" }, href: "/forecast?month=2026-10" },
    gm: { value: null, covered_engagements: 0, total_engagements: 1, revenue_coverage_pct: "0", confirmed_cost_engagements: 0, estimated_cost_engagements: 0, missing_cost_engagements: 1, comparison: { value: null, basis: "Prior-month comparison not recorded" }, href: "/portfolio?cost_coverage=covered", fix_href: "/settings/forecast" },
    backlog: { amount: "120000", engagements: 1, comparison: { value: null, basis: "Prior-month comparison not recorded" }, href: "/forecast?scenario=committed" },
    pipeline: { label: "Not yet in the SOW flow", weighted: "250000", gross: "500000", eligible_deals: 1, unscheduled_weighted: "250000", closed_won_gaps: 1, missing: [], comparison: { value: null, basis: "Prior-month comparison not recorded" }, href: "/pipeline?status=open&sow=none" },
    people: { billable_people: 4, billable_fte: "3.50", bench_people: 2, bench_basis: "active people without a current allocation", rolloffs_60_days: 1, open_seats: 1, open_seat_fte: "0.50", comparison: { value: 1, basis: "billable people versus prior month" }, billable_href: "/portfolio?people=billable", bench_href: "/people/supply?status=bench", rolloff_href: "/portfolio?view=rolloffs" },
  },
  metrics: { open_opportunity_value: "875000.50", open_opportunity_count: 3, open_opportunity_href: "/pipeline?status=open", open_opportunity_business_units: [], sows_in_progress: 2, committed_revenue: "120000", committed_gm_pct: null, planned_people: 4 },
  lifecycle: { pipeline: 1, sow_in_approval: 1, signed: 0, engagement_created: 1, active: 1, renewal_due: 0 },
  lifecycle_items: [
    { key: "pipeline", label: "Not yet in the SOW flow", count: 1, entity: "open deals", href: "/pipeline?status=open&sow=none" },
    { key: "sow_in_approval", label: "SOW in approval", count: 2, entity: "SOWs", href: "/sows?status=in_review&population_revision=revision-a" },
    { key: "signed", label: "Signed", count: 0, entity: "signed SOWs", href: "/sows?state=signed" },
    { key: "engagement_created", label: "Engagement created", count: 1, entity: "engagements", href: "/portfolio" },
    { key: "active", label: "Active", count: 1, entity: "engagements", href: "/projects" },
    { key: "renewal_due", label: "Renewal due", count: 0, entity: "renewal items", href: "/renewals?status=open" },
  ],
  revenue: { actual: null, remaining_signed: "120000", potential_expected: "250000", potential_upside: "250000", unscheduled_weighted_pipeline: "250000", currency: "USD", cost_coverage_complete: false, financial_blockers: ["rate missing"], months: [
    { month: "2026-10", actual: null, committed: "30000", expected_renewal: "0", pipeline_upside: "0", committed_total: "30000", expected_total: "30000", upside_total: "30000", remaining_signed: "30000", potential_expected: "0", potential_upside: "0" },
    { month: "2026-11", actual: null, committed: "35000", expected_renewal: "100000", pipeline_upside: "200000", committed_total: "35000", expected_total: "135000", upside_total: "335000", remaining_signed: "35000", potential_expected: "300000", potential_upside: "300000" },
    { month: "2026-12", actual: null, committed: "35000", expected_renewal: "150000", pipeline_upside: "300000", committed_total: "35000", expected_total: "185000", upside_total: "485000", remaining_signed: "35000", potential_expected: "450000", potential_upside: "450000" },
  ] },
  capacity: { month: "2026-11", locations: [{ location: "US", required_fte: "4", allocated_fte: "3.5", open_seat_fte: "0.5", people: 4, open_seats: 1, rolloffs: 1 }], required_fte: "4", allocated_fte: "3.5", gap_fte: "0.5", status: "attention", message: "0.50 FTE remains uncovered at peak demand.", gaps: [], source_status: "current", source_as_of: "2026-10-13T12:00:00Z", source_detail: "1 managed source reconciled with the allocation ledger" },
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
    expect(screen.getByText("Not calculated")).toBeVisible();
    expect(screen.getByText(/No current-month actuals/)).toBeVisible();
    expect(screen.queryAllByText("Unknown")).toHaveLength(0);
    expect(screen.getAllByRole("link", { name: /Revenue this month|GM this month|Signed backlog|Open opportunity value|Weighted · / })).toHaveLength(5);
    expect(screen.getByTestId("stage5-scope")).toHaveTextContent("HubSpot deals · Stage 5 and above");
    expect(screen.getByText("Open late-stage work, current-period wins and active delivery.")).toBeVisible();
    expect(screen.getByRole("columnheader", { name: "Business unit" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "ST21" })).toBeVisible();
  });

  it("filters accounts and exports through the shared business-unit scope", async () => {
    const user = userEvent.setup();
    renderPage();

    const accountBusinessUnit = await screen.findByRole("combobox", {
      name: "Filter accounts by business unit",
    });
    await user.selectOptions(accountBusinessUnit, "ST21");

    await waitFor(() =>
      expect(commandApi.getCommandAccounts).toHaveBeenLastCalledWith(
        expect.objectContaining({ business_unit: "ST21" }),
        expect.objectContaining({ page: 1, page_size: 25 }),
      ),
    );
    expect(commandApi.getCommandOverview).toHaveBeenLastCalledWith(
      expect.objectContaining({ business_unit: "ST21" }),
    );

    await user.click(screen.getByRole("button", { name: "Export this view" }));
    expect(commandApi.downloadCommandAccounts).toHaveBeenCalledWith(
      expect.objectContaining({ business_unit: "ST21" }),
      undefined,
      "all",
    );
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

  it("opens the canonical in-review population from the lifecycle count", async () => {
    renderPage();
    const link = await screen.findByRole("link", { name: /SOW in approval 2 SOWs/ });
    expect(link).toHaveAttribute(
      "href",
      "/sows?status=in_review&population_revision=revision-a",
    );
  });

  it("renders an assigned CEO approval supplied by the authoritative action queue", async () => {
    vi.mocked(commandApi.getCommandOverview).mockResolvedValueOnce({
      ...overview,
      actions: [
        ...overview.actions,
        {
          id: "approval:older-ceo:ceo",
          rank: 6,
          category: "Your SOW approval",
          account: "Older account",
          title: "Older CEO package",
          detail: "Ceo approval is waiting for you.",
          owner: "Avery Owner",
          due: "2026-10-20",
          href: "/sows/44444444-4444-4444-4444-444444444444/approvals",
          action: "Review SOW",
          impact: null,
          impact_label: null,
          period: "Current approval stage",
          missing_input: null,
        },
      ],
    });
    renderPage();
    expect(await screen.findByRole("link", { name: /Older account.*Older CEO package/ })).toHaveAttribute(
      "href",
      "/sows/44444444-4444-4444-4444-444444444444/approvals",
    );
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
    expect(screen.getByText("Three facts to act on")).toBeVisible();
  });

  it("shows the Pipeline's open number and names the stricter one (S23-PL2 B2)", async () => {
    renderPage();
    const open = await screen.findByRole("link", { name: /Open opportunity value/ });
    expect(open).toHaveAttribute("href", "/pipeline?status=open");
    expect(open).toHaveTextContent("$875,001");
    expect(open).toHaveTextContent("3 open deals · Hold included · unweighted");
    expect(open).toHaveTextContent("Same number as the Pipeline");
    const stricter = screen.getByRole("link", { name: /Weighted · 1 open deal/ });
    expect(stricter).toHaveTextContent("Not yet in the SOW flow");
    expect(stricter).not.toHaveTextContent("eligible open deal");
    expect(screen.queryByText("Weighted pipeline")).not.toBeInTheDocument();
    const lifecycle = screen.getByRole("link", { name: /Not yet in the SOW flow\s*1\s*open deals/ });
    expect(lifecycle).toHaveAttribute("href", "/pipeline?status=open&sow=none");
  });

  it("links the stricter number to the closest Pipeline list and says what differs (review R4)", async () => {
    renderPage();
    const stricter = await screen.findByRole("link", { name: /Weighted · 1 open deal/ });
    expect(stricter).toHaveAttribute("href", "/pipeline?status=open&sow=none");
    expect(stricter).toHaveTextContent(
      "Pipeline list: open deals with no SOW. This tile is weighted and leaves out deals linked to an engagement.",
    );
    expect(stricter).not.toHaveTextContent("Same number as the Pipeline");
    expect(screen.getByRole("link", { name: /weighted pipeline across 1 eligible deal/ })).toHaveAttribute(
      "href",
      "/pipeline?status=open&sow=none",
    );
  });

  it("names the business unit the open number covers when the scope is a HubSpot region (review R3/R4)", async () => {
    vi.mocked(commandApi.getCommandOverview).mockResolvedValueOnce({
      ...overview,
      tiles: { ...overview.tiles, pipeline: { ...overview.tiles.pipeline, href: "/pipeline?status=open&bu=IT+Avalon&sow=none" } },
      metrics: { ...overview.metrics, open_opportunity_count: 39, open_opportunity_href: "/pipeline?status=open&bu=IT+Avalon", open_opportunity_business_units: ["IT Avalon"] },
    });
    renderPage("/command?bu=US+-+IT+Avalon");
    const open = await screen.findByRole("link", { name: /Open opportunity value/ });
    expect(open).toHaveAttribute("href", "/pipeline?status=open&bu=IT+Avalon");
    expect(open).toHaveTextContent("39 open deals in IT Avalon · Hold included · unweighted");
    expect(open).toHaveTextContent("Same number as the Pipeline");
    const stricter = screen.getByRole("link", { name: /Weighted · 1 open deal/ });
    expect(stricter).toHaveTextContent("Pipeline list: open deals with no SOW in IT Avalon.");
  });

  it("says when a deal list has no business unit", async () => {
    vi.mocked(commandApi.getCommandOverview).mockResolvedValueOnce({
      ...overview,
      metrics: { ...overview.metrics, open_opportunity_href: "/pipeline?status=open&bu=unmapped", open_opportunity_business_units: ["unmapped"] },
    });
    renderPage("/command?bu=Brazil");
    const open = await screen.findByRole("link", { name: /Open opportunity value/ });
    expect(open).toHaveTextContent("3 open deals with no business unit · Hold included · unweighted");
  });

  it("shows the open number without the Pipeline claim when the owner has no HubSpot link (review R2/R3)", async () => {
    vi.mocked(commandApi.getCommandOverview).mockResolvedValueOnce({
      ...overview,
      brief: overview.brief.map((item) => (item.kind === "opportunity" ? { ...item, href: null } : item)),
      tiles: { ...overview.tiles, pipeline: { ...overview.tiles.pipeline, href: null } },
      metrics: { ...overview.metrics, open_opportunity_href: null },
      lifecycle_items: overview.lifecycle_items.map((item) => (item.key === "pipeline" ? { ...item, href: null } : item)),
    });
    renderPage("/command?owner=33333333-3333-3333-3333-333333333333");
    const figure = await screen.findByText("$875,001");
    expect(screen.queryByText("Same number as the Pipeline")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Open opportunity value/ })).not.toBeInTheDocument();
    const tile = figure.closest("[data-testid='tile']");
    expect(tile).toHaveTextContent("Open opportunity value");
    expect(tile).toHaveTextContent("3 open deals · Hold included · unweighted");
    expect(tile).toHaveTextContent("Not on the Pipeline: this owner has no HubSpot link");
    // The stricter tile, its lifecycle row and the brief line show their numbers without a link.
    expect(screen.queryByRole("link", { name: /Weighted · 1 open deal/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Weighted · 1 open deal/)).toBeVisible();
    expect(screen.queryByText(/^Pipeline list:/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Not yet in the SOW flow\s*1\s*open deals/ })).not.toBeInTheDocument();
    expect(screen.getAllByText("Not yet in the SOW flow").length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /weighted pipeline across 1 eligible deal/ })).not.toBeInTheDocument();
    expect(screen.getByText("250000.00 weighted pipeline across 1 eligible deal(s)")).toBeVisible();
  });
});

describe("S24-AG1 F7 · the NDA & MSA tile", () => {
  const withAttention = (count: number): commandApi.CommandOverview => ({
    ...overview,
    metrics: { ...overview.metrics, agreement_attention_clients: count, agreement_attention_href: "/agreements?status=attention" },
  });

  it("counts net-new clients past stage 1 without an NDA or MSA and opens NDA & MSA filtered to Needs attention", async () => {
    vi.mocked(commandApi.getCommandOverview).mockResolvedValue(withAttention(4));
    renderPage();
    const tile = await screen.findByRole("link", { name: /Net-new clients past stage 1 without an NDA or MSA/ });
    expect(tile).toHaveAttribute("href", "/agreements?status=attention");
    expect(tile).toHaveAttribute("data-testid", "tile");
    expect(tile).toHaveTextContent("Net-new clients past stage 1 without an NDA or MSA4");
    expect(tile).toHaveTextContent("Warn and flag only. Nothing is blocked anywhere.");
    expect(tile).toHaveTextContent("Counts every client");
    expect(tile).not.toHaveTextContent("do not apply");
    expect(tile).toHaveTextContent("Opens NDA & MSA filtered to “Needs attention”");
    expect(tile.className).toContain("border-warning/40");
  });

  it("says the dashboard's business unit and owner do not apply to it", async () => {
    vi.mocked(commandApi.getCommandOverview).mockResolvedValue(withAttention(4));
    renderPage("/command?bu=ST21");
    const tile = await screen.findByRole("link", { name: /Net-new clients past stage 1 without an NDA or MSA/ });
    expect(tile).toHaveTextContent("Counts every client: the business unit and owner selected here do not apply");
  });

  it("shows a real zero without the warning border", async () => {
    vi.mocked(commandApi.getCommandOverview).mockResolvedValue(withAttention(0));
    renderPage();
    const tile = await screen.findByRole("link", { name: /Net-new clients past stage 1 without an NDA or MSA/ });
    expect(tile).toHaveTextContent("without an NDA or MSA0");
    expect(tile.className).not.toContain("border-warning/40");
  });

  it("is left out when the API does not send the count (an older API during a deploy)", async () => {
    renderPage();
    expect(await screen.findByText("Open opportunity value")).toBeInTheDocument();
    expect(screen.queryByText("Net-new clients past stage 1 without an NDA or MSA")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("tile")).toHaveLength(5);
  });
});
