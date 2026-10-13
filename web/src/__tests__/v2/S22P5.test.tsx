/**
 * S22 P5 · business units, actuals, the forecast-model import. The API is
 * mocked at the module boundary; every number asserted below is the server's
 * (groups / totals / cards / actuals) — the browser adds nothing up.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import * as api from "../../api/engagements";
import * as clientApi from "../../api/client";
import { PortfolioPage } from "../../pages/v2/portfolio/PortfolioPage";
import { EngagementPage } from "../../pages/v2/portfolio/EngagementPage";
import { NewEngagementPage } from "../../pages/v2/portfolio/NewEngagementPage";
import { ImportForecastModelPage } from "../../pages/v2/portfolio/ImportForecastModelPage";

let groups = ["Delivery"];
vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => ({ user: { groups } }) }));

const here = dirname(fileURLToPath(import.meta.url));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
}

const engagement: api.Engagement = {
  id: "e1",
  client_id: "c1",
  client_name: "Gamma Health",
  hubspot_deal_id: null,
  opportunity_id: null,
  name: "VMS",
  type: "msp",
  start: "2026-04-01",
  end: "2027-03-31",
  total_price: null,
  monthly_fee: null,
  currency: "USD",
  additional_costs_flag: false,
  same_dates_for_all: true,
  owner_user_id: null,
  owner_name: null,
  status: "active",
  duration_months: 12,
  business_unit: "IT Avalon",
  sales_owner: "Jane Sales",
  delivery_owner: "Dev Lead",
  closed: false,
};

const allocation: api.Allocation = {
  id: "a1",
  engagement_id: "e1",
  resource_id: "r1",
  resource_name: "Developer",
  role: "Developer",
  seniority: "Mid",
  location: "India - Pune",
  employment_type: "w2_employee",
  assignment: null,
  utilization: 1,
  bill_rate: "5151.00",
  cost_per_hour: null,
  cost_per_hour_effective: null,
  burden_pct: 0.08,
  start: null,
  end: null,
  effective_start: "2026-04-01",
  effective_end: "2027-03-31",
  hours_override: null,
  superseded_by: null,
  rate_basis: "monthly",
  person: "Person 1",
  totals: { working_days: 250, hours: 2000, revenue: "61812.00", loaded_cost: "0.00", row_gm_pct: null, under_resource_floor: false },
};

const month = (key: string, actuals?: { hours: number; revenue: string; loss: string }): api.MonthLine => ({
  month: key,
  share_of_month: 1,
  people: 1,
  hours: 168,
  revenue: "5151.00",
  labour_cost: "0.00",
  burden_cost: "0.00",
  loaded_cost: "0.00",
  additional_costs: "0.00",
  pass_through_revenue: "0.00",
  total_revenue: "5151.00",
  total_cost: "0.00",
  gm: "5151.00",
  gm_pct: 1,
  actual_hours: actuals ? actuals.hours : null,
  actual_revenue: actuals ? actuals.revenue : null,
  billing_loss: actuals ? actuals.loss : null,
});

const forecast: api.Forecast = {
  engagement_id: "e1",
  duration_months: 12,
  status: "INCOMPLETE",
  project_floor_pct: 0.35,
  monthly_required: true,
  missing: ["Developer: cost per hour unknown"],
  totals: {
    hours: 2000,
    labour_cost: "0.00",
    burden_cost: "0.00",
    loaded_cost: "0.00",
    additional_costs: "0.00",
    pass_through_revenue: "0.00",
    total_revenue: "61812.00",
    total_cost: "0.00",
    gm: "61812.00",
    gm_pct: null,
  },
  staffing_totals: { hours: 2000, revenue: "61812.00", loaded_cost: "0.00", gm_pct: null },
  actuals: { months_with_actuals: 2, actual_revenue: "9800.00", forecast_in_actual_months: "10302.00", billing_loss: "502.00" },
  months: [month("2026-04", { hours: 160, revenue: "4900.00", loss: "251.00" }), month("2026-05", { hours: 152, revenue: "4900.00", loss: "251.00" }), month("2026-06")],
  by_assignment: {},
  allocation_months: [],
  location_check: {},
};

const noActuals: api.Forecast = {
  ...forecast,
  actuals: { months_with_actuals: 0, actual_revenue: "0.00", forecast_in_actual_months: "0.00", billing_loss: "0.00" },
  months: [month("2026-04"), month("2026-05"), month("2026-06")],
};

const row = (id: string, bu: api.BusinessUnit, client: string, name: string, revenue: string, cost: string): api.PortfolioRow => ({
  engagement_id: id,
  business_unit: bu,
  client_name: client,
  name,
  sales_owner: bu === "Retro Rabbit" ? null : "Jane Sales",
  delivery_owner: bu === "Retro Rabbit" ? null : "Dev Lead",
  type: "time_and_materials",
  start: "2026-04-01",
  end: "2027-03-31",
  people: 2,
  revenue_month: revenue,
  cost_month: cost,
  gm_pct_month: 0.4,
  gm_pct_term: 0.4,
  status: "PASS",
});

const allPortfolio: api.PortfolioForecast = {
  month: "2026-06",
  project_floor_pct: 0.35,
  cards: { portfolio_gm_pct: 0.41, below_floor: 1, rolloffs_60d: 0, bench: 0, billing_loss: { amount: "1250.00", forecast: "20000.00", billed: "18750.00", engagements: 2 } },
  rows: [
    row("e-st21-a", "ST21", "Costco", "Store systems", "100000.00", "60000.00"),
    row("e-st21-b", "ST21", "Alpha", "Portal", "50000.00", "30000.00"),
    row("e1", "IT Avalon", "Gamma Health", "VMS", "40000.00", "25000.00"),
    row("e-rr", "Retro Rabbit", "Zeta", "Studio", "10000.00", "5000.00"),
  ],
  groups: [
    { business_unit: "ST21", engagements: 2, people: 4, revenue: "150000.00", cost: "90000.00", gm_pct: 0.4, below_floor: 0 },
    { business_unit: "IT Avalon", engagements: 1, people: 2, revenue: "40000.00", cost: "25000.00", gm_pct: 0.375, below_floor: 1 },
    { business_unit: "Retro Rabbit", engagements: 1, people: 2, revenue: "10000.00", cost: "5000.00", gm_pct: 0.5, below_floor: 0 },
  ],
  totals: { people: 8, revenue: "200000.00", cost: "120000.00", gm_pct: 0.4 },
  rolloffs: [],
  bench_list: [],
};

const avalonPortfolio: api.PortfolioForecast = {
  ...allPortfolio,
  cards: { ...allPortfolio.cards, billing_loss: { amount: "0.00", forecast: "0.00", billed: "0.00", engagements: 0 } },
  rows: allPortfolio.rows.filter((r) => r.business_unit === "IT Avalon"),
  groups: allPortfolio.groups.filter((g) => g.business_unit === "IT Avalon"),
  totals: { people: 2, revenue: "40000.00", cost: "25000.00", gm_pct: 0.375 },
};

const dryRun: api.ForecastModelImportResult = {
  dry_run: true,
  report_markdown: "# Forecast model — dry run\n\nParsed **3 business units**.\n\n| Business unit | Clients |\n|---|---:|\n| ST21 | 2 |\n| IT Avalon | 1 |\n\n- Gamma Health-VMS: 1 person without a location",
  by_business_unit: [
    { business_unit: "ST21", clients: 2, engagements: 3, people: 12, closed: 1 },
    { business_unit: "IT Avalon", clients: 1, engagements: 1, people: 4, closed: 0 },
    { business_unit: "Retro Rabbit", clients: 1, engagements: 1, people: 2, closed: 0 },
  ],
  tabs: [
    { tab: "Costco", client: "Costco", business_unit: "ST21", engagement_type: "time_and_materials", engagements: 2, people: 9, allocations: 11, extensions: 2, months: 12, actual_months: 3, issues: [] },
    { tab: "Alpha", client: "Alpha", business_unit: "ST21", engagement_type: "staff_augmentation", engagements: 1, people: 3, allocations: 3, extensions: 0, months: 12, actual_months: 3, issues: [] },
    { tab: "Gamma Health-VMS", client: "Gamma Health", business_unit: "IT Avalon", engagement_type: "msp", engagements: 1, people: 4, allocations: 4, extensions: 0, months: 12, actual_months: 2, issues: ["1 person without a location"] },
    { tab: "Zeta", client: "Zeta", business_unit: "Retro Rabbit", engagement_type: "time_and_materials", engagements: 1, people: 2, allocations: 2, extensions: 0, months: 6, actual_months: 0, issues: [] },
  ],
  created: null,
};

const calendar: api.ForecastCalendar = {
  hours_per_day: 8,
  project_floor_pct: 0.35,
  locations: [{ name: "India - Pune", burden_pct_w2: 0.08, burden_pct_1099: 0.08, resource_floor_pct: 0.5 }],
  rate_card: [],
  holidays: {},
};

beforeEach(() => {
  groups = ["Delivery"];
  vi.spyOn(api, "getPortfolioForecast").mockImplementation(async (filters) => (filters.business_unit === "IT Avalon" ? avalonPortfolio : allPortfolio));
  vi.spyOn(api, "listClientOptions").mockResolvedValue([]);
  vi.spyOn(api, "listEngagements").mockResolvedValue({ total: 1, page: 1, page_size: 100, items: [engagement] });
  vi.spyOn(api, "getEngagement").mockResolvedValue(engagement);
  vi.spyOn(api, "listAllocations").mockResolvedValue([allocation]);
  vi.spyOn(api, "listCosts").mockResolvedValue([]);
  vi.spyOn(api, "getEngagementForecast").mockResolvedValue(forecast);
  vi.spyOn(api, "getForecastSettings").mockResolvedValue(calendar);
  vi.spyOn(api, "patchEngagement").mockResolvedValue(engagement);
  vi.spyOn(api, "patchAllocation").mockResolvedValue(allocation);
  vi.spyOn(api, "createEngagement").mockResolvedValue(engagement);
  vi.spyOn(api, "importForecastModel").mockImplementation(async (_file, dry) => (dry ? dryRun : { ...dryRun, dry_run: false, created: { clients: 4, engagements: 5, allocations: 20, actual_rows: 30 } }));
  vi.spyOn(clientApi, "getPipelineFacets").mockResolvedValue({ owners: [], business_units: [] });
  vi.spyOn(clientApi, "listPipelineOpportunities").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 } as unknown as Awaited<ReturnType<typeof clientApi.listPipelineOpportunities>>);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderPortfolio(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/portfolio/:bu" element={<PortfolioPage />} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  );
}

function renderEngagement(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/engagements/:id/:tab" element={<EngagementPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("S22 P5 · business units, actuals, import", () => {
  it("registers the BU routes, the import route and the nav entry", () => {
    const appTsx = readFileSync(resolve(here, "../../App.tsx"), "utf8");
    const nav = readFileSync(resolve(here, "../../ui-v2/PrimaryNavigation.tsx"), "utf8");
    expect(appTsx).toContain('path="/portfolio/:bu"');
    expect(appTsx).toContain('path="/import/forecast-model"');
    expect(nav).toMatch(/to: "\/import\/forecast-model", label: "Import the forecast model"/);
    expect(api.BU_SLUG["IT Avalon"]).toBe("it-avalon");
    expect(api.BU_FROM_SLUG["retro-rabbit"]).toBe("Retro Rabbit");
  });

  it("the All view groups rows by BU with a subtotal per BU from `groups` and the grand total from `totals`", async () => {
    renderPortfolio("/portfolio?month=2026-06");
    expect(await screen.findByRole("heading", { name: "Portfolio forecast" })).toBeInTheDocument();

    const tabs = within(screen.getByTestId("bu-tabs")).getAllByTestId("bu-tab");
    expect(tabs.map((t) => t.getAttribute("aria-label"))).toEqual(["All business units", "ST21", "IT Avalon", "Retro Rabbit"]);
    expect(tabs.map((t) => t.getAttribute("data-bu"))).toEqual(["", "ST21", "IT Avalon", "Retro Rabbit"]);
    expect(tabs[0]).toHaveAttribute("aria-pressed", "true");
    expect(within(tabs[0]).getByTestId("bu-tab-count")).toHaveTextContent("4");
    expect(within(tabs[1]).getByTestId("bu-tab-count")).toHaveTextContent("2");
    expect(within(tabs[2]).getByTestId("bu-tab-count")).toHaveTextContent("1");

    const headers = screen.getAllByTestId("bu-group");
    expect(headers.map((h) => h.getAttribute("data-bu"))).toEqual(["ST21", "IT Avalon", "Retro Rabbit"]);
    expect(headers[0]).toHaveTextContent("ST21 · 2 engagements");
    expect(headers[1]).toHaveTextContent("IT Avalon · 1 engagement");

    const subtotals = screen.getAllByTestId("bu-subtotal");
    expect(subtotals).toHaveLength(3);
    expect(subtotals[0]).toHaveTextContent("ST21 subtotal · Jun 2026");
    expect(within(subtotals[0]).getByTestId("subtotal-people")).toHaveTextContent("4");
    expect(within(subtotals[0]).getByTestId("subtotal-revenue")).toHaveTextContent("$150,000");
    expect(within(subtotals[0]).getByTestId("subtotal-cost")).toHaveTextContent("$90,000");
    expect(within(subtotals[0]).getByTestId("subtotal-gm")).toHaveTextContent("40.0%");
    expect(within(subtotals[1]).getByTestId("subtotal-gm")).toHaveTextContent("37.5%");
    expect(subtotals[1]).toHaveTextContent("1 below floor");

    const total = screen.getByTestId("portfolio-total");
    expect(total).toHaveTextContent("All business units · Jun 2026");
    expect(within(total).getByTestId("total-people")).toHaveTextContent("8");
    expect(within(total).getByTestId("total-revenue")).toHaveTextContent("$200,000");
    expect(within(total).getByTestId("total-cost")).toHaveTextContent("$120,000");
    expect(within(total).getByTestId("total-gm")).toHaveTextContent("40.0%");

    // Rows sit under their group header, owners under the engagement name.
    const rows = screen.getAllByTestId("portfolio-row");
    expect(rows).toHaveLength(4);
    expect(within(rows[0]).getByTestId("row-owners")).toHaveTextContent("Jane Sales · Dev Lead");
    expect(within(rows[3]).getByTestId("row-owners")).toHaveTextContent("— · —");
    const order = [...screen.getByRole("table", { name: "Portfolio forecast" }).querySelectorAll("tbody tr")].map((tr) => tr.getAttribute("data-testid"));
    expect(order).toEqual(["bu-group", "portfolio-row", "portfolio-row", "bu-subtotal", "bu-group", "portfolio-row", "bu-subtotal", "bu-group", "portfolio-row", "bu-subtotal", "portfolio-total"]);
    expect(api.getPortfolioForecast).toHaveBeenCalledWith({ month: "2026-06", business_unit: "", type: "", client_id: "" });
  });

  it("clicking a BU tab navigates to /portfolio/it-avalon, refetches with business_unit and shows only that BU's subtotal", async () => {
    renderPortfolio("/portfolio?month=2026-06");
    await screen.findByRole("heading", { name: "Portfolio forecast" });
    fireEvent.click(screen.getByRole("button", { name: "IT Avalon" }));
    expect(await screen.findByRole("heading", { name: "IT Avalon forecast" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/portfolio/it-avalon?month=2026-06");
    await waitFor(() => expect(api.getPortfolioForecast).toHaveBeenCalledWith({ month: "2026-06", business_unit: "IT Avalon", type: "", client_id: "" }));
    await waitFor(() => expect(screen.getAllByTestId("portfolio-row")).toHaveLength(1));
    expect(screen.queryAllByTestId("bu-group")).toHaveLength(0);
    const subtotals = screen.getAllByTestId("bu-subtotal");
    expect(subtotals).toHaveLength(1);
    expect(subtotals[0]).toHaveAttribute("data-bu", "IT Avalon");
    expect(subtotals[0]).toHaveTextContent("IT Avalon · Jun 2026");
    expect(within(subtotals[0]).getByTestId("subtotal-revenue")).toHaveTextContent("$40,000");
    expect(screen.queryByTestId("portfolio-total")).not.toBeInTheDocument();
    const avalonTab = screen.getByRole("button", { name: "IT Avalon" });
    expect(avalonTab).toHaveAttribute("aria-pressed", "true");
    // Tab counts still come from the all-BU response.
    await waitFor(() => expect(within(screen.getByRole("button", { name: "All business units" })).getByTestId("bu-tab-count")).toHaveTextContent("4"));
  });

  it("an unknown BU slug falls back to /portfolio", async () => {
    renderPortfolio("/portfolio/nope?month=2026-06");
    expect(await screen.findByRole("heading", { name: "Portfolio forecast" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/portfolio");
  });

  it("the Billing loss card reads the server's amount, forecast vs billed and engagement count — or says no actuals yet", async () => {
    renderPortfolio("/portfolio?month=2026-06");
    const card = await screen.findByTestId("card-billing-loss");
    expect(card).toHaveTextContent("Billing loss · months with actuals");
    expect(card).toHaveTextContent("$1,250");
    expect(card).toHaveTextContent("$20,000 forecast vs $18,750 billed · 2 engagements with actuals");
    cleanup();
    renderPortfolio("/portfolio/it-avalon?month=2026-06");
    const empty = await screen.findByTestId("card-billing-loss");
    expect(empty).toHaveTextContent("—");
    expect(empty).toHaveTextContent("no actuals loaded yet");
  });

  it("the engagement header shows the BU, owners and the CLOSED badge; Setup saves BU / owners / status via PATCH", async () => {
    vi.mocked(api.getEngagement).mockResolvedValue({ ...engagement, closed: true });
    renderEngagement("/engagements/e1/setup");
    const subtitle = await screen.findByTestId("engagement-subtitle");
    expect(subtitle).toHaveTextContent("IT Avalon · MSP · 2026-04-01 → 2027-03-31 · 12.00 months · sales Jane Sales · delivery Dev Lead · HubSpot: —");
    expect(screen.getByTestId("closed-badge")).toHaveTextContent("CLOSED");

    expect(screen.getByLabelText("Business unit")).toHaveValue("IT Avalon");
    expect(screen.getByLabelText("Sales owner")).toHaveValue("Jane Sales");
    expect(screen.getByLabelText("Delivery owner")).toHaveValue("Dev Lead");
    expect(screen.getByLabelText("Status")).toHaveValue("1");
    expect(within(screen.getByLabelText("Status")).getByRole("option", { name: "Closed — kept for history, off the portfolio" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Business unit"), { target: { value: "Retro Rabbit" } });
    await waitFor(() => expect(api.patchEngagement).toHaveBeenCalledWith("e1", { business_unit: "Retro Rabbit" }));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "0" } });
    await waitFor(() => expect(api.patchEngagement).toHaveBeenCalledWith("e1", { closed: false }));
    const sales = screen.getByLabelText("Sales owner");
    fireEvent.change(sales, { target: { value: "New Seller" } });
    fireEvent.blur(sales);
    await waitFor(() => expect(api.patchEngagement).toHaveBeenCalledWith("e1", { sales_owner: "New Seller" }));
  });

  it("an open engagement has no CLOSED badge", async () => {
    renderEngagement("/engagements/e1/forecast");
    await screen.findByTestId("engagement-subtitle");
    expect(screen.queryByTestId("closed-badge")).not.toBeInTheDocument();
  });

  it("the allocations grid puts Person first, has the per select, and an MSP without a fee shows the bill-rate columns", async () => {
    renderEngagement("/engagements/e1/allocations");
    const grid = await screen.findByRole("table", { name: "Allocations" });
    const headers = within(grid).getAllByRole("columnheader").map((th) => th.textContent);
    expect(headers[0]).toBe("Person");
    expect(headers[1]).toBe("Role");
    expect(headers).toContain("Bill rate");
    expect(headers[headers.indexOf("Bill rate") + 1]).toBe("per");
    expect(headers).toContain("Revenue");
    expect(headers).toContain("Row GM");
    expect(headers).not.toContain("Assignment"); // MSP is not an hourly type

    const row = screen.getByTestId("allocation-row");
    const person = within(row).getByLabelText("Person");
    expect(person).toHaveValue("Person 1");
    expect(person).toHaveAttribute("placeholder", "(name)");
    expect(within(row).getByText("Developer")).toBeInTheDocument(); // the planning resource label
    const basis = within(row).getByLabelText("Rate basis");
    expect(basis).toHaveValue("monthly");
    expect(within(basis).getAllByRole("option").map((o) => o.textContent)).toEqual(["per hour", "per day", "per month"]);
    expect(within(row).getByLabelText("Developer bill rate")).toHaveValue(5151);
    expect(within(row).getByText("$61,812")).toBeInTheDocument();

    fireEvent.change(basis, { target: { value: "daily" } });
    await waitFor(() => expect(api.patchAllocation).toHaveBeenCalledWith("a1", { rate_basis: "daily" }));
    fireEvent.change(person, { target: { value: "Person One" } });
    fireEvent.blur(person);
    await waitFor(() => expect(api.patchAllocation).toHaveBeenCalledWith("a1", { person: "Person One" }));
  });

  it("an MSP with a monthly fee hides the bill-rate columns", async () => {
    vi.mocked(api.getEngagement).mockResolvedValue({ ...engagement, monthly_fee: "42000.00" });
    renderEngagement("/engagements/e1/allocations");
    const grid = await screen.findByRole("table", { name: "Allocations" });
    const headers = within(grid).getAllByRole("columnheader").map((th) => th.textContent);
    expect(headers[0]).toBe("Person");
    expect(headers).not.toContain("Bill rate");
    expect(headers).not.toContain("per");
    expect(headers).not.toContain("Row GM");
  });

  it("the draft row has Person first and sends person + rate_basis on Add", async () => {
    vi.spyOn(api, "listResources").mockResolvedValue([]);
    vi.spyOn(api, "createResource").mockResolvedValue({ id: "r-new", name: "Asha", location: "India - Pune", employment_type: "w2_employee", seniority: "Mid", email: null, active: true });
    const addSpy = vi.spyOn(api, "addAllocation").mockResolvedValue(allocation);
    renderEngagement("/engagements/e1/allocations");
    fireEvent.click(await screen.findByRole("button", { name: /Add person/ }));
    const draft = await screen.findByTestId("draft-row");
    const cells = within(draft).getAllByRole("cell");
    expect(within(cells[0]).getByLabelText("Person")).toHaveAttribute("placeholder", "(name)");
    fireEvent.change(within(cells[0]).getByLabelText("Person"), { target: { value: "Asha" } });
    fireEvent.change(within(draft).getByLabelText("Bill rate"), { target: { value: "6325" } });
    fireEvent.change(within(draft).getByLabelText("Rate basis"), { target: { value: "monthly" } });
    fireEvent.click(within(draft).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(addSpy).toHaveBeenCalledWith("e1", expect.objectContaining({ resource_id: "r-new", person: "Asha", bill_rate: "6325", rate_basis: "monthly" })));
  });

  it("the Forecast tab shows the Actuals block only when months have actuals", async () => {
    renderEngagement("/engagements/e1/forecast");
    const block = await screen.findByTestId("actuals-block");
    expect(block).toHaveTextContent("Actuals · from timesheets / invoices · 2 months loaded");
    const rows = within(block).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Billed");
    expect(within(rows[1]).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Billed", "$4,900", "$4,900", "—", "$9,800"]);
    expect(within(rows[2]).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Actual hours", "160", "152", "—", ""]);
    expect(within(rows[3]).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Billing loss (forecast − billed)", "$251", "$251", "—", "$502"]);
    cleanup();
    vi.mocked(api.getEngagementForecast).mockResolvedValue(noActuals);
    renderEngagement("/engagements/e1/forecast");
    await screen.findByRole("table", { name: "All resources by month" });
    expect(screen.queryByTestId("actuals-block")).not.toBeInTheDocument();
  });

  it("a short engagement's term summary carries the actuals totals", async () => {
    vi.mocked(api.getEngagement).mockResolvedValue({ ...engagement, type: "assessment", total_price: "10000.00", start: "2026-04-01", end: "2026-05-31" });
    vi.mocked(api.getEngagementForecast).mockResolvedValue({ ...forecast, duration_months: 2, monthly_required: false, months: forecast.months.slice(0, 2) });
    renderEngagement("/engagements/e1/forecast");
    await screen.findByTestId("term-summary");
    const block = screen.getByTestId("actuals-block");
    expect(block).toHaveTextContent("Billed$9,800");
    expect(block).toHaveTextContent("Billing loss (forecast − billed)$502");
  });

  it("the New engagement form carries Business unit (default ST21) and the owners onto POST /engagements", async () => {
    render(
      <MemoryRouter initialEntries={["/engagements/new"]}>
        <NewEngagementPage />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "New engagement" });
    expect(screen.getByLabelText("Business unit")).toHaveValue("ST21");
    fireEvent.change(screen.getByLabelText("Business unit"), { target: { value: "Retro Rabbit" } });
    fireEvent.change(screen.getByLabelText("Sales owner"), { target: { value: "Jane Sales" } });
    fireEvent.change(screen.getByLabelText("Delivery owner"), { target: { value: "Dev Lead" } });
    fireEvent.change(screen.getByLabelText("Client *"), { target: { value: "__new" } });
    fireEvent.change(screen.getByLabelText("New client name"), { target: { value: "Zeta" } });
    vi.spyOn(api, "createClient").mockResolvedValue({ id: "c-z", name: "Zeta", source: "manual" });
    fireEvent.change(screen.getByLabelText("Engagement name *"), { target: { value: "Studio" } });
    fireEvent.change(screen.getByLabelText("Engagement type *"), { target: { value: "time_and_materials" } });
    fireEvent.change(screen.getByLabelText("Start *"), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText("End *"), { target: { value: "2027-04-30" } });
    fireEvent.change(screen.getByLabelText("Additional costs? *"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("Same start/end for everyone? *"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create engagement" }));
    await waitFor(() =>
      expect(api.createEngagement).toHaveBeenCalledWith(expect.objectContaining({ client_id: "c-z", business_unit: "Retro Rabbit", sales_owner: "Jane Sales", delivery_owner: "Dev Lead" })),
    );
  });

  it("the import page dry-runs the workbook, shows cards / table / report, and Load posts dry_run=false then lands on /portfolio", async () => {
    render(
      <MemoryRouter initialEntries={["/import/forecast-model"]}>
        <Routes>
          <Route path="/import/forecast-model" element={<ImportForecastModelPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: "Import the forecast model" })).toBeInTheDocument();
    expect(screen.getByText(/Dry run first — nothing is created until you confirm/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "1 · Upload the workbook" })).toBeInTheDocument();
    expect(screen.queryByTestId("dry-run-cards")).not.toBeInTheDocument();

    const file = new File([new Uint8Array([80, 75, 3, 4])], "ST21_FY2526_Forecast_Model_Master.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const input = screen.getByLabelText("Forecast model (.xlsx)");
    expect(input).toHaveAttribute("accept", expect.stringContaining(".xlsx"));
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(api.importForecastModel).toHaveBeenCalledWith(file, true));

    expect(await screen.findByRole("heading", { name: "2 · Dry run — what would be created" })).toBeInTheDocument();
    const cards = within(screen.getByTestId("dry-run-cards")).getAllByTestId("dry-run-card");
    expect(cards.map((c) => c.getAttribute("data-bu"))).toEqual(["ST21", "IT Avalon", "Retro Rabbit"]);
    expect(cards[0]).toHaveTextContent("ST21");
    expect(cards[0]).toHaveTextContent("2");
    expect(cards[0]).toHaveTextContent("3 engagements · 12 people · 1 closed");

    const tabs = screen.getByTestId("dry-run-tabs");
    expect(within(tabs).getAllByRole("columnheader").map((th) => th.textContent)).toEqual([
      "Tab",
      "Client (dashboard)",
      "BU",
      "Type",
      "Engagements",
      "People",
      "Allocations (ext.)",
      "Months (with actuals)",
      "Needs attention",
    ]);
    const gamma = within(tabs).getAllByTestId("dry-run-tab")[2];
    expect(within(gamma).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Gamma Health-VMS", "Gamma Health", "IT Avalon", "MSP", "1", "4", "4 (0)", "12 (2)", "1 person without a location"]);
    expect(within(within(tabs).getAllByTestId("dry-run-tab")[0]).getAllByRole("cell")[8]).toHaveTextContent("—");

    const report = screen.getByTestId("dry-run-report");
    expect(within(report).getByRole("heading", { name: "Forecast model — dry run" })).toBeInTheDocument();
    expect(within(report).getByText("3 business units").tagName).toBe("STRONG");
    expect(within(report).getByRole("table")).toBeInTheDocument();
    expect(screen.getByText(/Not loaded from this workbook/)).toBeInTheDocument();

    const load = screen.getByRole("button", { name: /^Load / });
    expect(load).toHaveTextContent("Load 18 people into 4 clients");
    fireEvent.click(load);
    await waitFor(() => expect(api.importForecastModel).toHaveBeenCalledWith(file, false));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/portfolio"));
    expect(await screen.findByRole("heading", { name: "Portfolio forecast" })).toBeInTheDocument();
  });

  it("a workbook the server rejects shows its errors and offers no Load button", async () => {
    const error = Object.assign(new Error("422"), { status: 422, body: { detail: { errors: ["Not a forecast model master: no run-rate dashboard tab."] } } });
    vi.mocked(api.importForecastModel).mockRejectedValue(error);
    render(
      <MemoryRouter initialEntries={["/import/forecast-model"]}>
        <ImportForecastModelPage />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "Import the forecast model" });
    fireEvent.change(screen.getByLabelText("Forecast model (.xlsx)"), { target: { files: [new File(["x"], "random.xlsx")] } });
    expect(await screen.findByTestId("import-errors")).toHaveTextContent("Not a forecast model master: no run-rate dashboard tab.");
    expect(screen.queryByRole("button", { name: /^Load / })).not.toBeInTheDocument();
  });
});
