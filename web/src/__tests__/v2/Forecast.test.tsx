import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ForecastPage } from "../../pages/v2/Forecast";
import { RevenueChart } from "../../pages/v2/forecast/RevenueChart";
import * as api from "../../api/forecast";
import * as peopleDemand from "../../api/people-demand";
import * as clientApi from "../../api/client";

const period = (start: string, revenue = "24000") => ({
  start,
  end_exclusive: "2028-01-01",
  revenue,
  signed: "24000",
  potential: "147000",
  expected: "171000",
  cost: null,
  gm: null,
});
function outlook(): api.ForecastOutlook {
  return {
    schema_version: "forecast-outlook-v1",
    as_of: "2026-10-01T00:00:00Z",
    timezone: "America/New_York",
    currency: "USD",
    scenario: "expected",
    future_quarters: 4,
    current_month: period("2026-10-01"),
    current_quarter: period("2026-10-01"),
    future: period("2027-01-01", "147000"),
    quarters: [],
    months: Array.from({ length: 15 }, (_, i) =>
      period(
        `${i < 3 ? "2026" : "2027"}-${String(i < 3 ? i + 10 : i - 2).padStart(2, "0")}-01`,
      ),
    ),
    accounts: [
      {
        account_id: "account-x",
        name: "Company X",
        current_month: period("2026-10-01"),
        current_quarter: period("2026-10-01"),
        future: period("2027-01-01"),
        quarters: [],
      },
    ],
    rows: [
      {
        row_id: "row1",
        account_id: "account-x",
        source_id: "plan",
        source_version: "v1",
        scope_id: "scope",
        month: "2027-12-01",
        lifecycle: "tentative",
        revenue: "49000",
        signed: "0",
        potential: "49000",
        currency: "USD",
        cost: null,
      },
    ],
    excluded: [],
    unresolved_sources: [],
    pending_sources: [],
    source_watermark: "watermark-123",
    scope_label: "Company total",
    source_count: 1,
    stale: false,
    source_coverage: "Tenant-bound commercial schedules and versioned plans",
    legacy_sources_included: false,
    actuals_available: false,
    actuals_basis: "service_schedule",
  };
}
function mount(
  url = "/forecast?future_quarters=4&as_of=2026-10-01T00%3A00%3A00Z",
) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <ForecastPage />
    </MemoryRouter>,
  );
}
beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "getForecastOutlook").mockResolvedValue(outlook());
  vi.spyOn(api, "getForecastPlans").mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    size: 50,
  });
});
describe("Forecast", () => {
  it("clears a selected month only when the returned horizon no longer includes it", async () => {
    vi.mocked(api.getForecastOutlook).mockImplementation(async (filters) => ({
      ...outlook(), future_quarters: filters.future_quarters,
      months: outlook().months.slice(0, filters.future_quarters === 1 ? 6 : 15),
    }));
    mount("/forecast?view=revenue&future_quarters=4&month=2027-12-01");
    await screen.findByRole("region", { name: "Monthly revenue projection" });
    expect(screen.getByRole("button", { name: "Clear month filter" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Future quarters"), { target: { value: "1" } });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Clear month filter" })).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "January 2027" }));
    fireEvent.change(screen.getByLabelText("Future quarters"), { target: { value: "4" } });
    await waitFor(() => expect(api.getForecastOutlook).toHaveBeenCalledTimes(3));
    expect(screen.getByRole("button", { name: "Clear month filter" })).toHaveTextContent("January 2027");
  });
  it("keeps financial measure bases distinct from scheduled revenue", async () => {
    vi.mocked(api.getForecastOutlook).mockResolvedValue({ ...outlook(), actuals_available: true,
      actuals_basis: "Separate financial measures; service schedule unchanged",
      financial_actuals: { cutoff: "2026-10-01", blended_with_forecast: false, excluded: [], totals: [
        { period_month: "2026-10-01", measure: "recognized_revenue", currency: "USD", amount: "12000.01" },
        { period_month: "2026-10-01", measure: "cash_collected", currency: "USD", amount: "8000" },
      ] } });
    mount();
    const table = await screen.findByRole("region", { name: "Financial actuals" });
    expect(table).toHaveTextContent("Recognized revenue");
    expect(table).toHaveTextContent("Cash collected");
    expect(table).toHaveTextContent("12000.01");
    expect(table).toHaveTextContent("8000");
  });
  it("gives positive revenue bars definite pixel heights without a percentage-height parent dependency", () => {
    const onMonth = vi.fn();
    render(<RevenueChart currency="USD" onMonth={onMonth} months={[
      { ...period("2026-11-01"), signed: "0", potential: "35000" },
      { ...period("2026-12-01"), signed: "17500", potential: "35000" },
    ]} />);
    const november = screen.getByRole("button", { name: "Inspect November 2026" });
    const december = screen.getByRole("button", { name: "Inspect December 2026" });
    expect(november.querySelector("span.bg-sky-600")).toHaveStyle({ height: "184px" });
    expect(november.querySelector("span.bg-emerald-600")).toHaveStyle({ height: "0px" });
    expect(december.querySelector("span.bg-emerald-600")).toHaveStyle({ height: "92px" });
    expect(november).toHaveAttribute("title", "November 2026: signed 0, potential 35000 USD");
    fireEvent.click(december);
    expect(onMonth).toHaveBeenCalledWith("2026-12-01");
  });
  it("does not attach a newer plan version's assumptions to an older calculated row", async () => {
    vi.mocked(api.getForecastPlans).mockResolvedValue({
      items: [
        {
          id: "plan",
          version_id: "v2",
          version: 2,
          account_id: "account-x",
          account_name: "Company X",
          opportunity_id: null,
          source_status: "Local forecast only",
          owner_id: "owner",
          title: "Newer plan title",
          lifecycle: "tentative",
          probability: "0.7",
          probability_source: "Owner estimate",
          assumptions: ["NEWER UNCALCULATED ASSUMPTION"],
          scope_id: "scope",
          job: null,
        },
      ],
      total: 1,
      page: 1,
      size: 50,
    });
    mount("/forecast?view=revenue&future_quarters=4");
    fireEvent.click(
      await screen.findByRole("button", { name: "Planning source" }),
    );
    expect(
      screen.getByRole("region", { name: "Source detail" }),
    ).toHaveTextContent("v1");
    expect(
      screen.queryByText("NEWER UNCALCULATED ASSUMPTION"),
    ).not.toBeInTheDocument();
  });
  it("defaults to two future quarters and a live server as-of", async () => {
    mount("/forecast");
    await screen.findByText("Company total");
    expect(api.getForecastOutlook).toHaveBeenCalledWith(
      {
        scenario: "expected",
        future_quarters: 2,
        account_id: undefined,
        as_of: undefined,
      },
      expect.any(AbortSignal),
    );
    expect(
      screen.getByRole("tab", { name: "Company & accounts" }),
    ).toHaveAttribute("aria-selected", "true");
  });
  it("drills into authoritative named source, calculation identity and evidence", async () => {
    const response = outlook();
    response.rows[0] = {
      ...response.rows[0],
      source_name: "Modern workplace rollout",
      source_url: "/deals/deal-one",
      calculation_version: "commercial-schedule-v1",
      assumptions: ["Customer start remains provisional"],
      source_evidence: ["Roadmap page 4"],
    };
    vi.mocked(api.getForecastOutlook).mockResolvedValue(response);
    mount("/forecast?view=revenue&future_quarters=4");
    fireEvent.click(
      await screen.findByRole("button", { name: "Modern workplace rollout" }),
    );
    expect(
      screen.getByRole("link", { name: "Modern workplace rollout" }),
    ).toHaveAttribute("href", "/deals/deal-one");
    expect(
      screen.getByRole("region", { name: "Source detail" }),
    ).toHaveTextContent("commercial-schedule-v1");
    expect(screen.getByText("Roadmap page 4")).toBeInTheDocument();
    expect(
      screen.getByText("Customer start remains provisional"),
    ).toBeInTheDocument();
  });
  it("defaults to company/accounts and keeps all 15 months and chosen scenario on account drilldown", async () => {
    mount();
    expect(
      await screen.findByRole("tab", { name: "Company & accounts" }),
    ).toHaveAttribute("aria-selected", "true");
    fireEvent.click(await screen.findByRole("button", { name: "Company X" }));
    await waitFor(() =>
      expect(api.getForecastOutlook).toHaveBeenLastCalledWith(
        expect.objectContaining({
          account_id: "account-x",
          scenario: "expected",
          future_quarters: 4,
          as_of: "2026-10-01T00:00:00Z",
        }),
        expect.any(AbortSignal),
      ),
    );
    fireEvent.click(screen.getByRole("tab", { name: "Revenue projection" }));
    expect(
      await screen.findByRole("button", { name: "December 2027" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", {
        name: /^(January|February|March|April|May|June|July|August|September|October|November|December) 202[67]$/,
      }),
    ).toHaveLength(15);
    fireEvent.click(screen.getByRole("button", { name: "December 2027" }));
    expect(await screen.findAllByText("49000")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Planning source" }));
    expect(
      screen.getByRole("region", { name: "Source detail" }),
    ).toHaveTextContent("v1");
  });
  it("exports only supplied authorized rows and protects CSV cells without converting Decimal strings", () => {
    const row = {
      ...outlook().rows[0],
      source_id: "=HYPERLINK(unsafe)",
      revenue: "12345678901234567890.0123456789",
    };
    delete row.cost;
    const csv = api.forecastCsv([row], {
      ...outlook(),
      scope_label: "My portfolio",
    });
    expect(csv).toContain("12345678901234567890.0123456789");
    expect(csv).toContain("'=HYPERLINK(unsafe)");
    expect(csv.split("\r\n")).toHaveLength(2);
    expect(csv.split("\r\n")[0]).not.toContain('"cost"');
    expect(csv).toContain("My portfolio");
  });
  it("uses source pagination metadata without replacing forecast totals", async () => {
    vi.mocked(api.getForecastPlans).mockResolvedValue({
      items: [],
      total: 51,
      page: 1,
      size: 50,
    });
    mount();
    fireEvent.click(
      await screen.findByRole("button", { name: "Next source page" }),
    );
    await waitFor(() =>
      expect(api.getForecastPlans).toHaveBeenLastCalledWith(
        { account_id: undefined, page: 2, size: 50 },
        expect.any(AbortSignal),
      ),
    );
    expect(
      screen.queryByText("No accounts in this scope."),
    ).not.toBeInTheDocument();
  });
  it("ignores an older response after a scenario change", async () => {
    let resolveOld!: (value: api.ForecastOutlook) => void;
    vi.mocked(api.getForecastOutlook)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOld = resolve;
          }),
      )
      .mockResolvedValue({
        ...outlook(),
        scenario: "upside",
        scope_label: "My portfolio",
      });
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Upside" }));
    await screen.findByText("My portfolio");
    await act(async () =>
      resolveOld({ ...outlook(), scope_label: "STALE COMPANY TOTAL" }),
    );
    expect(screen.queryByText("STALE COMPANY TOTAL")).not.toBeInTheDocument();
  });
  it("reports failures as errors rather than an empty portfolio", async () => {
    vi.mocked(api.getForecastOutlook).mockRejectedValue(
      new Error("Reporting currency is not configured"),
    );
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Reporting currency is not configured",
    );
    expect(
      screen.queryByText("No accounts in this scope."),
    ).not.toBeInTheDocument();
  });
  it("shows restricted costs, unavailable actuals and unresolved/pending sources without inventing zero", async () => {
    const response = outlook();
    delete response.future.cost;
    delete response.future.gm;
    response.pending_sources = ["pending-version"];
    response.unresolved_sources = [
      {
        source_id: "unknown",
        source_version: "v2",
        account_id: "account-x",
        name: "Missing staffing cost",
        reasons: ["Loaded rate is unresolved"],
      },
    ];
    vi.mocked(api.getForecastOutlook).mockResolvedValue(response);
    mount();
    await screen.findByText("Actuals unavailable");
    expect(screen.getAllByText("Restricted").length).toBeGreaterThan(0);
    expect(screen.getByText("Loaded rate is unresolved")).toBeInTheDocument();
    expect(screen.getByText("pending-version")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("1 pending / 1 unresolved / 0 excluded");
  });
  it("opens the persisted resource-demand view without a revenue chart", async () => {
    vi.spyOn(clientApi, "getMe").mockResolvedValue({ id: "delivery", email: "delivery@example.test", name: "Delivery", groups: ["Delivery"] });
    const demand = vi.spyOn(peopleDemand, "getDemandSources").mockResolvedValue({
      schema_version: "people-demand-v1", items: [], scope_label: "Company demand", is_reservation: false,
    });
    mount("/forecast?view=resources&account_id=account-x");
    expect(await screen.findByText("No demand sources")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Resource demand" })).toHaveAttribute("aria-selected", "true");
    expect(demand).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("region", { name: "Signed and potential revenue chart" })).not.toBeInTheDocument();
  });
});
