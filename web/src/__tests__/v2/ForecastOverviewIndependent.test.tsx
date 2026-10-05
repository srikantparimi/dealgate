import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/forecast";
import { ForecastPage } from "../../pages/v2/Forecast";

// Literal boundary fixtures, not an oracle derived from production calculations.
function period(start = "2027-01-01", end = "2027-04-01"): api.ForecastPeriod {
  return { start, end_exclusive: end, revenue: "36924.125", signed: "10000.125",
    potential: "26924", expected: "36924.125", cost: null, cost_complete: false,
    known_cost: "500.25", gm: null, signed_coverage: "0.27083", provisional: "26924" };
}
function outlook(): api.ForecastOutlook {
  const currentMonth = { ...period("2026-10-01", "2026-11-01"), revenue: "812.50" };
  const currentQuarter = { ...period("2026-10-01", "2027-01-01"), revenue: "1625" };
  return {
    schema_version: "forecast-outlook-v1", as_of: "2026-10-15T18:00:00Z",
    timezone: "America/Los_Angeles", currency: "USD", scenario: "expected", future_quarters: 1,
    current_month: currentMonth, current_quarter: currentQuarter, future: period(),
    quarters: [currentQuarter, period()], months: [period("2027-01-01", "2027-02-01")],
    accounts: [{ account_id: "account-a", name: "Independent Account", current_month: currentMonth,
      current_quarter: currentQuarter, future: period(), quarters: [currentQuarter, period()] }],
    rows: [{ row_id: "row-1", account_id: "account-a", source_id: "plan-1", source_version: "version-3",
      scope_id: "scope-growth", month: "2027-01-01", lifecycle: "tentative", revenue: "26924",
      signed: "0", potential: "26924", currency: "USD", probability: "0.7", cost: null,
      source_name: "Follow-on delivery", source_url: "/deals/deal-1", calculation_version: "calc-v7",
      original_currency: "EUR", fx_version: "approved-rate-17", fx_date: "2026-09-29",
      assumptions: ["Start is subject to client approval"], source_evidence: ["Assessment page 7"] },
    { row_id: "row-2", account_id: "account-a", source_id: "signed-1", source_version: "signed-v2",
      scope_id: "scope-signed", month: "2027-01-01", lifecycle: "signed", revenue: "10000.125",
      signed: "10000.125", potential: "0", currency: "USD", source_name: "Current contract" }],
    excluded: [], unresolved_sources: [], pending_sources: [], source_watermark: "qa-watermark-17",
    scope_label: "My portfolio", source_count: 2, stale: false, source_coverage: "Authorized service schedules",
    legacy_sources_included: false, actuals_available: false, actuals_basis: "service_schedule",
  };
}
function plans(): api.ForecastPlans {
  return { total: 1, page: 1, size: 50, items: [{ id: "plan-1", version_id: "version-3", version: 3,
    account_id: "account-a", account_name: "Independent Account", opportunity_id: "deal-1",
    source_status: "Linked CRM deal", owner_id: "owner-1", title: "Follow-on delivery",
    lifecycle: "tentative", probability: "0.7", probability_source: "Owner estimate",
    assumptions: ["Start is subject to client approval"], scope_id: "scope-growth",
    job: { id: "job-1", status: "done", attempts: 1, next_attempt_at: null, last_error: null } }] };
}
function Location() {
  return <output aria-label="Current URL">{useLocation().search}</output>;
}
function mount(query = "view=overview&future_quarters=1") {
  return render(<MemoryRouter initialEntries={[`/forecast?${query}`]}><ForecastPage /><Location /></MemoryRouter>);
}
function metric(label: string) {
  return within(screen.getByRole("region", { name: "Future planning basis" })).getByText(label).nextElementSibling;
}
async function ready() {
  return screen.findByRole("region", { name: "Forecast overview" });
}
beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "getForecastOutlook").mockResolvedValue(outlook());
  vi.spyOn(api, "getForecastPlans").mockResolvedValue(plans());
});

describe("Independent Forecast Overview boundaries", () => {
  it("uses authorized server aggregates rather than reconstructing them from the current plan page", async () => {
    vi.mocked(api.getForecastPlans).mockResolvedValue({ items: [], total: 51, page: 3, size: 50 });
    mount("view=overview&page=3");
    const overview = await ready();
    expect(overview).toHaveTextContent("USD 36924.125");
    expect(overview).toHaveTextContent("USD 812.50");
    expect(overview).toHaveTextContent("0 of 51 planning sources / Page 3");
    expect(overview).not.toHaveTextContent("No planning sources in this scope");
    expect(screen.getByRole("button", { name: "Next source page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous source page" })).not.toBeDisabled();
    expect(screen.queryByText("Company total")).not.toBeInTheDocument();
  });

  it("preserves scenario, date, horizon and month when selecting an account and resets only plan paging", async () => {
    mount("view=overview&scenario=upside&future_quarters=4&as_of=2026-10-15T18%3A00%3A00Z&month=2027-01-01&page=2");
    const sources = within(await screen.findByRole("region", { name: "Overview sources" }));
    await act(async () => { fireEvent.click(sources.getAllByRole("button", { name: "Independent Account" })[0]); });
    const query = new URLSearchParams(screen.getByLabelText("Current URL").textContent!);
    expect(Object.fromEntries(query)).toEqual({ view: "overview", scenario: "upside", future_quarters: "4",
      as_of: "2026-10-15T18:00:00Z", month: "2027-01-01", account_id: "account-a" });
    expect(api.getForecastOutlook).toHaveBeenLastCalledWith({ account_id: "account-a", scenario: "upside",
      future_quarters: 4, as_of: "2026-10-15T18:00:00Z" }, expect.any(AbortSignal));
    expect(api.getForecastPlans).toHaveBeenLastCalledWith({ account_id: "account-a", page: 1, size: 50 }, expect.any(AbortSignal));
  });

  it("removes only the month chip across a view switch", async () => {
    mount("view=overview&account_id=account-a&scenario=committed&future_quarters=4&month=2027-01-01");
    await ready();
    fireEvent.click(screen.getByRole("tab", { name: "Revenue projection" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear month filter" }));
    expect(Object.fromEntries(new URLSearchParams(screen.getByLabelText("Current URL").textContent!)))
      .toEqual({ view: "revenue", account_id: "account-a", scenario: "committed", future_quarters: "4" });
  });

  it("does not infer restricted cost or GM from visible revenue or include cost in exports", async () => {
    const data = outlook();
    for (const item of [data.future, data.current_month, data.current_quarter, ...data.months,
      ...data.quarters, ...data.accounts.flatMap(account => [account.future, account.current_month, account.current_quarter, ...account.quarters])]) {
      delete item.cost; delete item.gm; delete item.known_cost; delete item.cost_complete;
    }
    data.rows.forEach(row => { delete row.cost; });
    vi.mocked(api.getForecastOutlook).mockResolvedValue(data);
    mount(); await ready();
    expect(metric("Estimated delivery cost")).toHaveTextContent("Restricted");
    expect(metric("Planning GM")).toHaveTextContent("Restricted");
    expect(api.forecastCsv(data.rows, data).split("\r\n")[0]).not.toContain('"cost"');
    expect(screen.queryByText("500.25")).not.toBeInTheDocument();
  });

  it("does not turn unknown delivery cost into a complete zero-cost margin", async () => {
    mount(); await ready();
    expect(metric("Estimated delivery cost")).toHaveTextContent("Unresolved");
    expect(metric("Planning GM")).toHaveTextContent("Unassessed");
    expect(metric("Planning GM")).not.toHaveTextContent("100%");
  });

  it("labels signed coverage N/A when Expected revenue is zero", async () => {
    const data = outlook();
    data.future = { ...period(), revenue: "0", signed: "0", potential: "0", expected: "0", signed_coverage: null };
    vi.mocked(api.getForecastOutlook).mockResolvedValue(data);
    mount(); await ready();
    expect(metric("Signed coverage / Expected basis")).toHaveTextContent("N/A");
  });

  it("keeps stale, failed and excluded sources visible without inventing fresh success", async () => {
    const data = outlook(); data.stale = true; data.pending_sources = ["pending-v9"];
    data.unresolved_sources = [{ source_id: "unpriced", source_version: "v4", account_id: "account-a",
      name: "Unpriced extension", reasons: ["Missing reporting FX"] }];
    data.excluded = [{ row_id: "lost-row", source_id: "lost", source_name: "Declined option", account_id: "account-a",
      month: "2027-01-01", reasons: ["Closed lost"] }];
    const sourcePlans = plans(); sourcePlans.items[0].job = { id: "job-1", status: "failed", attempts: 5,
      next_attempt_at: null, last_error: "Commercial inputs require review" };
    vi.mocked(api.getForecastOutlook).mockResolvedValue(data); vi.mocked(api.getForecastPlans).mockResolvedValue(sourcePlans);
    mount(); const overview = await ready();
    expect(overview).toHaveTextContent("Calculation pending: pending-v9");
    expect(overview).toHaveTextContent("Missing reporting FX");
    expect(overview).toHaveTextContent("Commercial inputs require review");
    expect(screen.getByRole("region", { name: "Forecast exceptions" })).toHaveTextContent("Source updates pending");
    expect(screen.getByRole("region", { name: "Forecast exceptions" })).toHaveTextContent("Closed lost");
  });

  it("keeps authority on server 403 and discards previously visible source detail", async () => {
    mount(); await ready();
    fireEvent.click(within(screen.getByRole("region", { name: "Overview sources" })).getByRole("button", { name: "Follow-on delivery" }));
    expect(screen.getByRole("region", { name: "Source detail" })).toBeInTheDocument();
    vi.mocked(api.getForecastOutlook).mockRejectedValue(new Error("403 Financial outlook permission required"));
    fireEvent.click(screen.getByRole("button", { name: "Refresh forecast" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("403 Financial outlook permission required");
    expect(screen.queryByRole("region", { name: "Source detail" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Forecast overview" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export rows" })).toBeDisabled();
  });

  it("ignores a stale rejected request after a newer scope succeeds", async () => {
    let rejectOld!: (error: Error) => void;
    vi.mocked(api.getForecastOutlook).mockImplementationOnce(() => new Promise((_, reject) => { rejectOld = reject; }))
      .mockResolvedValue({ ...outlook(), scenario: "upside" });
    mount(); fireEvent.click(screen.getByRole("button", { name: "Upside" })); await ready();
    await act(async () => rejectOld(new Error("OLD PERMISSION ERROR")));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Forecast overview" })).toHaveTextContent("USD 36924.125");
  });

  it("uses exact source identity and evidence independently of which plan page is loaded", async () => {
    vi.mocked(api.getForecastPlans).mockResolvedValue({ items: [], total: 51, page: 2, size: 50 });
    mount("view=overview&page=2"); await ready();
    fireEvent.click(within(screen.getByRole("region", { name: "Overview sources" })).getByRole("button", { name: "Follow-on delivery" }));
    const detail = screen.getByRole("region", { name: "Source detail" });
    expect(detail).toHaveTextContent("version-3"); expect(detail).toHaveTextContent("calc-v7");
    expect(detail).toHaveTextContent("Assessment page 7");
    expect(within(detail).getByRole("link", { name: "Follow-on delivery" })).toHaveAttribute("href", "/deals/deal-1");
  });

  it("shows the supplied original currency and FX date alongside the conversion version", async () => {
    mount(); await ready();
    fireEvent.click(within(screen.getByRole("region", { name: "Overview sources" })).getByRole("button", { name: "Follow-on delivery" }));
    const detail = screen.getByRole("region", { name: "Source detail" });
    expect(detail).toHaveTextContent("approved-rate-17");
    expect(detail).toHaveTextContent("EUR");
    expect(detail).toHaveTextContent("2026-09-29");
  });

  it("exports the supplied timezone and row FX basis for reproducible reporting", () => {
    const data = outlook(); const csv = api.forecastCsv(data.rows, data);
    expect(csv).toContain('"America/Los_Angeles"');
    expect(csv).toContain('"EUR"'); expect(csv).toContain('"approved-rate-17"'); expect(csv).toContain('"2026-09-29"');
  });

  it("renders financial actuals separately instead of adding them to the service aggregate", async () => {
    const data = outlook(); data.actuals_available = true;
    data.financial_actuals = { cutoff: "2026-10-15", blended_with_forecast: false, excluded: [], totals: [
      { period_month: "2026-10-01", measure: "billed_revenue", currency: "USD", amount: "923.456" } ] };
    vi.mocked(api.getForecastOutlook).mockResolvedValue(data);
    mount(); const overview = await ready();
    expect(screen.getByRole("region", { name: "Financial actuals" })).toHaveTextContent("923.456");
    expect(overview).toHaveTextContent("USD 812.50"); expect(overview).not.toHaveTextContent("1735.956");
  });

  it("does not call a missing source endpoint result an empty authorized portfolio", async () => {
    vi.mocked(api.getForecastPlans).mockRejectedValue(new Error("Planning sources unavailable"));
    mount(); await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Planning sources unavailable"));
    expect(screen.queryByText("No planning sources in this scope.")).not.toBeInTheDocument();
    expect(screen.queryByText("No accounts in this scope.")).not.toBeInTheDocument();
  });
});
