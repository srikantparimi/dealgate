import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/forecast";
import { ForecastPage } from "../../pages/v2/Forecast";

const period: api.ForecastPeriod = {
  start: "2027-01-01",
  end_exclusive: "2027-07-01",
  revenue: "12345.678901",
  signed: "2345.600001",
  potential: "10000.078900",
  expected: "12345.678901",
  cost: null,
  gm: null,
  signed_coverage: "0.19",
};
function outlook(): api.ForecastOutlook {
  return {
    schema_version: "forecast-outlook-v1",
    as_of: "2026-10-01T00:00:00Z",
    timezone: "UTC",
    currency: "USD",
    scenario: "expected",
    future_quarters: 2,
    current_month: { ...period, start: "2026-10-01", revenue: "111.123456" },
    current_quarter: { ...period, start: "2026-10-01", revenue: "222.123456" },
    future: period,
    quarters: [],
    months: [period],
    accounts: [
      {
        account_id: "account-x",
        name: "Company X",
        current_month: period,
        current_quarter: period,
        future: period,
        quarters: [],
      },
    ],
    rows: [
      {
        row_id: "row-a",
        account_id: "account-x",
        source_id: "source-a",
        source_version: "v1",
        scope_id: "scope-a",
        month: "2027-01-01",
        lifecycle: "signed",
        revenue: "555.000001",
        signed: "555.000001",
        potential: "0",
        currency: "USD",
        source_name: "Assessment A",
        source_evidence: ["Signed appendix page 4"],
        calculation_version: "engine-a",
      },
    ],
    excluded: [],
    unresolved_sources: [],
    pending_sources: [],
    source_watermark: "watermark-a",
    scope_label: "My portfolio",
    source_count: 1,
    stale: false,
    source_coverage: "Authorized sources",
    legacy_sources_included: false,
    actuals_available: false,
    actuals_basis: "service_schedule",
  };
}
function Location() {
  return <output aria-label="Location">{useLocation().search}</output>;
}
function mount() {
  render(
    <MemoryRouter
      initialEntries={[
        "/forecast?view=overview&scenario=expected&future_quarters=4&as_of=2026-10-01T00%3A00%3A00Z",
      ]}
    >
      <ForecastPage />
      <Location />
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
describe("Forecast Overview", () => {
  it("displays server aggregate decimals, separate periods and honest unavailable dependencies", async () => {
    mount();
    expect(
      await screen.findByRole("tab", { name: "Overview" }),
    ).toHaveAttribute("aria-selected", "true");
    const overview = await screen.findByRole("region", {
      name: "Forecast overview",
    });
    expect(overview).toHaveTextContent("12345.678901");
    expect(overview).toHaveTextContent("111.123456");
    expect(overview).toHaveTextContent("222.123456");
    expect(overview).toHaveTextContent("10000.078900");
    expect(overview).toHaveTextContent("Unresolved");
    expect(overview).toHaveTextContent("Expiry risk unavailable");
    expect(overview).toHaveTextContent(
      "Assessment-to-project linkage unavailable",
    );
    expect(screen.getByText("My portfolio")).toBeInTheDocument();
  });
  it("drills into authorized source evidence and preserves URL filters on account selection", async () => {
    mount();
    const overview = await screen.findByRole("region", {
      name: "Forecast overview",
    });
    fireEvent.click(
      within(overview).getByRole("button", { name: "Assessment A" }),
    );
    expect(
      await screen.findByRole("region", { name: "Source detail" }),
    ).toHaveTextContent("Signed appendix page 4");
    await act(async () => {
      fireEvent.click(
        within(overview).getByRole("button", { name: "Company X" }),
      );
    });
    expect(screen.getByLabelText("Location")).toHaveTextContent(
      "account_id=account-x",
    );
    expect(screen.getByLabelText("Location")).toHaveTextContent(
      "future_quarters=4",
    );
    expect(screen.getByLabelText("Location")).toHaveTextContent(
      "view=overview",
    );
    expect(screen.getByLabelText("Location")).toHaveTextContent(
      "scenario=expected",
    );
  });
  it("does not replace restricted aggregates or incomplete source coverage with zero", async () => {
    const data = outlook();
    delete data.future.cost;
    delete data.future.gm;
    data.pending_sources = ["waiting-version"];
    data.unresolved_sources = [
      {
        source_id: "missing",
        source_version: "v2",
        account_id: "account-x",
        name: "Unpriced renewal",
        reasons: ["Probability not confirmed"],
      },
    ];
    vi.mocked(api.getForecastOutlook).mockResolvedValue(data);
    mount();
    const overview = await screen.findByRole("region", {
      name: "Forecast overview",
    });
    expect(within(overview).getAllByText("Restricted")).toHaveLength(2);
    expect(overview).toHaveTextContent("Probability not confirmed");
    expect(overview).toHaveTextContent("waiting-version");
  });
  it("shows plan assumptions without pretending a paginated plan subset is all decisions", async () => {
    vi.mocked(api.getForecastPlans).mockResolvedValue({
      total: 51,
      page: 1,
      size: 50,
      items: [
        {
          id: "plan-a",
          version_id: "v3",
          version: 3,
          account_id: "account-x",
          account_name: "Company X",
          opportunity_id: "deal-a",
          source_status: "Linked CRM deal",
          owner_id: "owner-a",
          title: "Potential delivery",
          lifecycle: "draft",
          probability: null,
          probability_source: null,
          assumptions: ["Client scope confirmation needed"],
          scope_id: "scope-b",
          job: null,
        },
      ],
    });
    mount();
    const overview = await screen.findByRole("region", {
      name: "Forecast overview",
    });
    expect(overview).toHaveTextContent("Client scope confirmation needed");
    expect(overview).toHaveTextContent("1 of 51 planning sources");
    expect(
      within(overview).getByRole("link", { name: "Potential delivery" }),
    ).toHaveAttribute("href", "/deals/deal-a");
  });
  it("keeps API failure visible instead of showing an empty overview", async () => {
    vi.mocked(api.getForecastOutlook).mockRejectedValue(
      new Error("Forecast access denied"),
    );
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Forecast access denied",
    );
    expect(
      screen.queryByRole("region", { name: "Forecast overview" }),
    ).not.toBeInTheDocument();
  });
});
