import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ForecastOutlook } from "../../api/forecast";
import { CurrentEstimate } from "../../pages/v2/forecast/CurrentEstimate";

function data(): ForecastOutlook {
  return {
    accounts: [{ account_id: "client", name: "Coverage Company" }],
    current_period_estimate: {
      cutoff: "2026-10-02", currency: "USD",
      totals: { revenue: "23000.99", cost: "11000", profit: "12000.99", gm_pct: "0.52176" },
      excluded: [{ id: "invoice", reason: "Financial measure remains separate from service estimate" }],
      rows: [{ row_id: "gm:0", source_id: "gm", source_version: "signed-version", account_id: "client", month: "2026-10-01",
        revenue: { scheduled: "24000", actual_to_date: "11000.99", covered_fraction: "0.5", uncovered_forecast: "12000", estimate: "23000.99", actual_ids: ["recognized"] },
        cost: { scheduled: "10000", actual_to_date: "6000", covered_fraction: "0.5", uncovered_forecast: "5000", estimate: "11000", actual_ids: ["cost"] },
      }],
    },
  } as ForecastOutlook;
}

describe("Current-period signed estimate", () => {
  it("shows exact matched actuals and uncovered forecast separately from the original schedule", () => {
    render(<CurrentEstimate data={data()} />);
    const revenue = screen.getByRole("row", { name: /Coverage Company.*Recognized revenue/ });
    for (const value of ["24000", "11000.99", "12000", "23000.99"]) {
      expect(within(revenue).getByText(value, { exact: true })).toBeInTheDocument();
    }
    expect(screen.getByText("Estimated profit")).toBeInTheDocument();
    expect(screen.getByText("12000.99")).toBeInTheDocument();
    expect(screen.getByText(/invoice: Financial measure remains separate/)).toBeInTheDocument();
  });

  it("does not invent matched actuals or margin when cost is unknown", () => {
    const input = data();
    input.current_period_estimate!.rows[0].cost = { scheduled: null, actual_to_date: "0", covered_fraction: "0", uncovered_forecast: null, estimate: null, actual_ids: [] };
    input.current_period_estimate!.totals = { revenue: "23000.99", cost: null, profit: null, gm_pct: null };
    render(<CurrentEstimate data={input} />);
    expect(screen.getByText("No matched actuals")).toBeInTheDocument();
    expect(screen.getAllByText("Unassessed")).toHaveLength(2);
  });

  it("renders no financial estimate when the API does not grant it", () => {
    const input = data();
    delete input.current_period_estimate;
    render(<CurrentEstimate data={input} />);
    expect(screen.queryByRole("region", { name: "Current-period signed estimate" })).not.toBeInTheDocument();
  });
});
