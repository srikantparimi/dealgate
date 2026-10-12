/**
 * S22 · Portfolio & Forecast screens render the server's numbers and wire
 * the prototype's controls. The API is mocked at the module boundary — these
 * tests check what the owner sees (cards, totals row, status line, tabs,
 * Leaves / Re-hire / remove), not arithmetic (there is none in the browser).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import * as api from "../../api/engagements";
import * as clientApi from "../../api/client";
import { PortfolioPage } from "../../pages/v2/portfolio/PortfolioPage";
import { EngagementPage } from "../../pages/v2/portfolio/EngagementPage";
import { NewEngagementPage } from "../../pages/v2/portfolio/NewEngagementPage";

let groups = ["Delivery"];
vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => ({ user: { groups } }) }));

const here = dirname(fileURLToPath(import.meta.url));

const engagement: api.Engagement = {
  id: "e1",
  client_id: "c1",
  client_name: "Client A",
  hubspot_deal_id: "123",
  opportunity_id: null,
  name: "Portal & data platform staffing",
  type: "staff_augmentation",
  start: "2026-11-02",
  end: "2027-04-30",
  total_price: null,
  monthly_fee: null,
  currency: "USD",
  additional_costs_flag: true,
  same_dates_for_all: false,
  owner_user_id: null,
  owner_name: "Adil Lalji",
  status: "active",
  duration_months: 5.966667,
};

const allocation: api.Allocation = {
  id: "a1",
  engagement_id: "e1",
  resource_id: "r1",
  resource_name: "Developer 1",
  role: "Developer",
  seniority: "Senior",
  location: "US",
  employment_type: "w2_employee",
  assignment: "Portal rebuild",
  utilization: 1,
  bill_rate: "135.00",
  cost_per_hour: "70.00",
  cost_per_hour_effective: "70.00",
  burden_pct: 0.36,
  start: null,
  end: null,
  effective_start: "2026-11-02",
  effective_end: "2027-04-30",
  hours_override: null,
  superseded_by: null,
  totals: { working_days: 124, hours: 992, revenue: "133920.00", loaded_cost: "94438.40", row_gm_pct: 0.2948, under_resource_floor: true },
};

const month = (key: string): api.MonthLine => ({
  month: key,
  share_of_month: 1,
  people: 1,
  hours: 160,
  revenue: "21600.00",
  labour_cost: "11200.00",
  burden_cost: "4032.00",
  loaded_cost: "15232.00",
  additional_costs: "600.00",
  pass_through_revenue: "0.00",
  total_revenue: "21600.00",
  total_cost: "15832.00",
  gm: "5768.00",
  gm_pct: 0.267,
});

const forecast: api.Forecast = {
  engagement_id: "e1",
  duration_months: 5.966667,
  status: "BELOW FLOOR",
  project_floor_pct: 0.35,
  monthly_required: true,
  missing: [],
  totals: {
    hours: 992,
    labour_cost: "69440.00",
    burden_cost: "24998.40",
    loaded_cost: "94438.40",
    additional_costs: "3600.00",
    pass_through_revenue: "0.00",
    total_revenue: "133920.00",
    total_cost: "98038.40",
    gm: "35881.60",
    gm_pct: 0.2679,
  },
  staffing_totals: { hours: 992, revenue: "133920.00", loaded_cost: "94438.40", gm_pct: 0.2948 },
  months: [month("2026-11"), month("2026-12")],
  by_assignment: { "Portal rebuild": { "2026-11": { people: 1, hours: 160, revenue: "21600.00", loaded_cost: "15232.00", gm_pct: 0.2948 } } },
  by_assignment_totals: { "Portal rebuild": { people: 1, hours: 992, revenue: "133920.00", loaded_cost: "94438.40", gm_pct: 0.2948 } },
  allocation_months: [{ allocation_id: "a1", resource_name: "Developer 1", assignment: "Portal rebuild", month: "2026-11", working_days: 20, hours: 160, revenue: "21600.00", loaded_cost: "15232.00" }],
  location_check: { US: { revenue: "133920.00", loaded_cost: "94438.40", gm_pct: 0.2948, floor: 0.35, ok: false } },
};

const portfolio: api.PortfolioForecast = {
  month: "2026-11",
  project_floor_pct: 0.35,
  cards: { portfolio_gm_pct: 0.267, below_floor: 1, rolloffs_60d: 1, bench: 1 },
  rows: [
    {
      engagement_id: "e1",
      client_name: "Client A",
      name: engagement.name,
      type: "staff_augmentation",
      start: engagement.start,
      end: engagement.end,
      people: 1,
      revenue_month: "21600.00",
      cost_month: "15832.00",
      gm_pct_month: 0.267,
      gm_pct_term: 0.2679,
      status: "BELOW FLOOR",
    },
  ],
  totals: { people: 1, revenue: "21600.00", cost: "15832.00", gm_pct: 0.267 },
  rolloffs: [{ engagement_id: "e1", allocation_id: "a1", client: "Client A", resource: "Developer 1", role: "Developer", assignment: "Portal rebuild", end: "2026-12-31" }],
  bench_list: [{ resource_id: "r2", resource: "Priya N.", location: "India", employment_type: "w2_employee", seniority: "Mid", free_from: "2026-11-01" }],
};

const calendar: api.ForecastCalendar = {
  hours_per_day: 8,
  project_floor_pct: 0.35,
  locations: [{ name: "US", burden_pct_w2: 0.36, burden_pct_1099: 0.05, resource_floor_pct: 0.35 }],
  rate_card: [{ seniority: "Senior", location: "US", employment_type: "w2_employee", cost_per_hour: "100.00" }],
  holidays: { US: ["2026-11-26"] },
};

beforeEach(() => {
  groups = ["Delivery"];
  vi.spyOn(api, "getPortfolioForecast").mockResolvedValue(portfolio);
  vi.spyOn(api, "listClientOptions").mockResolvedValue([{ id: "c1", name: "Client A", source: "manual" }]);
  vi.spyOn(api, "listEngagements").mockResolvedValue({ total: 1, page: 1, page_size: 100, items: [engagement] });
  vi.spyOn(api, "getEngagement").mockResolvedValue(engagement);
  vi.spyOn(api, "listAllocations").mockResolvedValue([allocation]);
  vi.spyOn(api, "listCosts").mockResolvedValue([]);
  vi.spyOn(api, "getEngagementForecast").mockResolvedValue(forecast);
  vi.spyOn(api, "getForecastSettings").mockResolvedValue(calendar);
  vi.spyOn(api, "closeAllocation").mockResolvedValue({ ...allocation, end: "2026-12-31" });
  vi.spyOn(api, "rehireAllocation").mockResolvedValue({ ...allocation, id: "a2", start: "2027-01-01" });
  vi.spyOn(api, "createEngagement").mockResolvedValue(engagement);
  vi.spyOn(api, "createClient").mockResolvedValue({ id: "c-new", name: "Brand New Co", source: "manual" });
  vi.spyOn(clientApi, "getPipelineFacets").mockResolvedValue({ owners: [], business_units: [] });
  vi.spyOn(clientApi, "listPipelineOpportunities").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as unknown as Awaited<ReturnType<typeof clientApi.listPipelineOpportunities>>);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("S22 · route table and navigation", () => {
  const appTsx = readFileSync(resolve(here, "../../App.tsx"), "utf8");
  const nav = readFileSync(resolve(here, "../../ui-v2/PrimaryNavigation.tsx"), "utf8");
  it("registers /portfolio, /engagements/new and /engagements/:id/:tab", () => {
    expect(appTsx).toContain('path="/portfolio"');
    expect(appTsx).toContain('path="/engagements/new"');
    expect(appTsx).toContain('path="/engagements/:id/:tab"');
  });
  it("puts Portfolio forecast in the Operations group", () => {
    expect(nav).toMatch(/to: "\/portfolio", label: "Portfolio forecast"/);
  });
});

describe("S22 · PortfolioPage", () => {
  it("shows the four cards, the table, the totals row and the panels from the server", async () => {
    render(
      <MemoryRouter initialEntries={["/portfolio?month=2026-11"]}>
        <PortfolioPage />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: "Portfolio forecast" })).toBeInTheDocument();
    expect(screen.getByTestId("card-gm")).toHaveTextContent("26.7%");
    expect(screen.getByTestId("card-below_floor")).toHaveTextContent("1");
    expect(screen.getByTestId("card-rolloffs")).toHaveTextContent("1");
    expect(screen.getByTestId("card-bench")).toHaveTextContent("1");
    const totals = screen.getByTestId("portfolio-totals");
    expect(totals).toHaveTextContent("Portfolio · Nov 2026");
    expect(totals).toHaveTextContent("$21,600");
    expect(totals).toHaveTextContent("$15,832");
    expect(within(screen.getByRole("table", { name: "Roll-offs" })).getByText("Developer 1")).toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: "Bench" })).getByText("Priya N.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New engagement/ })).toBeInTheDocument();
    expect(api.getPortfolioForecast).toHaveBeenCalledWith({ month: "2026-11", type: "", client_id: "" });
  });

  it("the Below floor card filters the table to the rows it counts", async () => {
    render(
      <MemoryRouter initialEntries={["/portfolio?month=2026-11"]}>
        <PortfolioPage />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByTestId("card-below_floor"));
    expect(await screen.findByText(/Showing the 1 engagement below the project floor/)).toBeInTheDocument();
  });
});

describe("S22 · EngagementPage", () => {
  function renderAt(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/engagements/:id" element={<EngagementPage />} />
          <Route path="/engagements/:id/:tab" element={<EngagementPage />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("renders the header, status line and allocations grid with Row GM red under the floor", async () => {
    renderAt("/engagements/e1/allocations");
    expect(await screen.findByTestId("engagement-heading")).toHaveTextContent("Client A · Portal & data platform staffing");
    const status = screen.getByTestId("status-line");
    expect(status).toHaveTextContent("BELOW FLOOR");
    expect(status).toHaveTextContent("GM 26.8%");
    expect(status).toHaveTextContent("US resources 29.5% vs 35.0% · review rates");
    expect(screen.getByRole("tab", { name: "Allocations" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Forecast" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Setup & costs" })).toBeInTheDocument();
    const row = screen.getByTestId("allocation-row");
    expect(within(row).getByText("Developer 1")).toBeInTheDocument();
    expect(within(row).getByTestId("row-gm")).toHaveClass("text-danger");
    expect(screen.getByTestId("allocations-totals")).toHaveTextContent("992");
    expect(within(row).getByRole("button", { name: "Leaves" })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Re-hire" })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Remove Developer 1" })).toBeInTheDocument();
  });

  it("Leaves closes the row and Re-hire copies it, through the API", async () => {
    renderAt("/engagements/e1");
    const row = await screen.findByTestId("allocation-row");
    fireEvent.click(within(row).getByRole("button", { name: "Leaves" }));
    await waitFor(() => expect(api.closeAllocation).toHaveBeenCalledWith("a1"));
    fireEvent.click(within(row).getByRole("button", { name: "Re-hire" }));
    await waitFor(() => expect(api.rehireAllocation).toHaveBeenCalledWith("a1"));
    expect(api.getEngagementForecast).toHaveBeenCalledTimes(3); // initial + after each change
  });

  it("the Forecast tab shows the monthly-required line, the all-resources block and the assignment block", async () => {
    renderAt("/engagements/e1/forecast");
    expect(await screen.findByTestId("monthly-required")).toHaveTextContent("Monthly view required — 6.0 months.");
    const all = screen.getByRole("table", { name: "All resources by month" });
    expect(within(all).getByText("Labour + burden")).toBeInTheDocument();
    expect(within(all).getAllByText("$21,600").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Portal rebuild" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Per person · revenue by month/ })).toBeInTheDocument();
  });

  it("a Sales user sees no per-person cost but can still edit the ledger", async () => {
    groups = ["Sales"];
    vi.mocked(api.listAllocations).mockResolvedValue([{ ...allocation, cost_per_hour: undefined, cost_per_hour_effective: undefined, burden_pct: undefined, totals: { working_days: 124, hours: 992, revenue: "133920.00" } }]);
    renderAt("/engagements/e1/allocations");
    const row = await screen.findByTestId("allocation-row");
    expect(within(row).getByText("restricted")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Leaves" })).toBeInTheDocument();
  });

  it("an HR reader has no edit controls", async () => {
    groups = ["HR"];
    renderAt("/engagements/e1/allocations");
    const row = await screen.findByTestId("allocation-row");
    expect(within(row).queryByRole("button", { name: "Leaves" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add person/ })).not.toBeInTheDocument();
  });
});

describe("S22 · NewEngagementPage", () => {
  it("lists the sheet's project-block fields, greys money fields by type and reports what is missing", async () => {
    render(
      <MemoryRouter initialEntries={["/engagements/new"]}>
        <NewEngagementPage />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: "New engagement" })).toBeInTheDocument();
    expect(screen.getByLabelText("Total project price")).toBeDisabled();
    expect(screen.getByLabelText("Monthly fee")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Engagement type *"), { target: { value: "msp" } });
    expect(screen.getByLabelText("Monthly fee")).toBeEnabled();
    expect(screen.getByLabelText("Total project price")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Create engagement" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Missing: client, name, dates, monthly fee, additional costs Y/N, same dates Y/N");
    expect(api.createEngagement).not.toHaveBeenCalled();
  });

  it("creates a new client on the way when '+ New client…' is chosen", async () => {
    render(
      <MemoryRouter initialEntries={["/engagements/new"]}>
        <NewEngagementPage />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "New engagement" });
    fireEvent.change(screen.getByLabelText("Client *"), { target: { value: "__new" } });
    fireEvent.change(screen.getByLabelText("New client name"), { target: { value: "Brand New Co" } });
    fireEvent.change(screen.getByLabelText("Engagement name *"), { target: { value: "Support" } });
    fireEvent.change(screen.getByLabelText("Engagement type *"), { target: { value: "msp" } });
    fireEvent.change(screen.getByLabelText("Start *"), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText("End *"), { target: { value: "2027-04-30" } });
    fireEvent.change(screen.getByLabelText("Monthly fee"), { target: { value: "42000" } });
    fireEvent.change(screen.getByLabelText("Additional costs? *"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("Same start/end for everyone? *"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create engagement" }));
    await waitFor(() => expect(api.createClient).toHaveBeenCalledWith("Brand New Co"));
    await waitFor(() => expect(api.createEngagement).toHaveBeenCalledWith(expect.objectContaining({ client_id: "c-new", type: "msp", monthly_fee: "42000", same_dates_for_all: true, additional_costs_flag: false })));
  });
});
