import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FinanceGmPanel } from "../../pages/v2/sow-workspace/staffing/FinanceGmPanel";

const result = {
  gm_version: 4, gm_us: "0.4040000000", gm_india: null, gm_blended: "0.4040000000",
  us_floor: "0.35", india_floor: "0.50", us_pass: true, india_pass: true,
  us_applicable: true, india_applicable: false, us_delta: "0.054", failing: [],
  finance_summary: { revenue: "50000.00", labor_cost: "28800.00", direct_cost: "1000.00",
    total_delivery_cost: "29800.00", gross_profit: "20200.00", labor_pct: "0.576",
    direct_pct: "0.02", total_cost_pct: "0.596", pass_through: "2300.00" },
};

describe("Finance GM presentation", () => {
  it("shows server cost amounts and ratios with the applicable floor and pass-through subtotal", () => {
    const { container } = render(<FinanceGmPanel result={result} />);
    for (const text of ["$50,000", "$28,800", "$1,000", "$29,800", "$20,200", "57.6% of price", "2.0% of price", "59.6% of price", "$2,300", "GM v4 · draft", "Passes US floor", "Not applicable — no India resources"]) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
    expect(screen.getAllByRole("meter")).toHaveLength(1);
    expect(container.textContent).not.toMatch(/0\.\d{6,}/);
  });

  it("keeps the server failure even when rounded margin appears at the floor", () => {
    render(<FinanceGmPanel result={{ ...result, gm_us: "0.349999999999999999", us_pass: false, us_delta: "-0.000000000000000001", failing: ["US"] }} />);
    expect(screen.getByTestId("staffing-floor-summary")).toHaveTextContent("Fails · US");
    expect(screen.getByTestId("floorbar-chip")).toHaveTextContent("Fails by 0.0 pts");
  });

  it("shows both floors for a mixed model and honest missing data", () => {
    const { rerender } = render(<FinanceGmPanel result={{ ...result, gm_india: "0.55", india_applicable: true }} />);
    expect(screen.getAllByRole("meter")).toHaveLength(2);
    expect(screen.getByText("Passes both floors")).toBeInTheDocument();
    rerender(<FinanceGmPanel result={{ ...result, gm_us: null }} />);
    expect(screen.getByTestId("staffing-floor-summary")).toHaveTextContent("GM unavailable");
  });

  it("does not present partial staffing costs as a passing margin", () => {
    render(<FinanceGmPanel result={{ ...result, complete: false }} />);
    expect(screen.getByTestId("staffing-floor-summary")).toHaveTextContent("Incomplete staffing costs");
    expect(screen.queryByText("40.4%")).not.toBeInTheDocument();
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
  });
});
