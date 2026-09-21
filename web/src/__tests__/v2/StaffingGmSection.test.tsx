import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SowConfirmationPayload } from "../../api/client";
import { StaffingGmSection } from "../../pages/v2/sow-studio/confirmation/StaffingGmSection";

function fixture(type = "fixed_price"): SowConfirmationPayload {
  return {
    engagement: { primary: { type, confidence: 1 } },
    staffing: {
      lines: [{
        role: "Engineer", seniority: "Senior", location: "US",
        hourly_cost: "120.0000", hourly_bill_rate: "0.0000",
        hours_billable: "80.0000", allocation_pct: "1.0000",
        provenance: "manual", source_id: null, warning: null,
        start_date: null, end_date: null,
      }],
      warnings: [], notes: [], sources: [],
    },
    gm_model: { id: "gm-1", engagement_type: type, revenue_us: "50000.00", revenue_india: null, resource_line_count: 1 },
    floors: {
      us_pass: true, india_pass: true, requires_ceo: false, failing: [],
      gm_us: "0.4240000000", gm_india: null, gm_blended: "0.4240000000",
    },
  } as unknown as SowConfirmationPayload;
}

describe("S13b confirmation presentation", () => {
  it("shows the entered cost rate and formatted fixed-price values", () => {
    const { container } = render(<StaffingGmSection payload={fixture()} />);
    expect(screen.getByText("Cost /hr")).toBeInTheDocument();
    expect(screen.getByText("$120.00")).toBeInTheDocument();
    expect(screen.getByText("— fixed price")).toBeInTheDocument();
    expect(screen.getByText("80")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getAllByText("42.4%")).toHaveLength(2);
    expect(screen.getByText("$50,000")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/0\.\d{6,}/);
    expect(container.textContent).not.toContain("0.0000");
    expect(screen.getByText("Not applicable — no India resources")).toBeInTheDocument();
    expect(screen.getByTestId("staffing-floor-summary")).toHaveTextContent("Passes US floor");
    expect(screen.getAllByRole("meter")).toHaveLength(1);
  });

  it("shows both rates for T&M", () => {
    const payload = fixture("time_and_materials");
    payload.staffing.lines[0].hourly_bill_rate = "180.0000";
    render(<StaffingGmSection payload={payload} />);
    expect(screen.getByText("$180.00")).toBeInTheDocument();
    expect(screen.getByText("$120.00")).toBeInTheDocument();
    expect(screen.queryByText("— fixed price")).not.toBeInTheDocument();
  });

  it("keeps both floor bars for a mixed plan", () => {
    const payload = fixture();
    payload.staffing.lines.push({ ...payload.staffing.lines[0], location: "India" });
    payload.floors.gm_india = "0.5500000000";
    payload.floors.revenue_total = "145000.00";
    render(<StaffingGmSection payload={payload} />);
    expect(screen.getAllByRole("meter")).toHaveLength(2);
    expect(screen.getByText("55.0%")).toBeInTheDocument();
    expect(screen.getByText("$145,000")).toBeInTheDocument();
    expect(screen.getByText("50% floor")).toBeInTheDocument();
    expect(screen.getByTestId("staffing-floor-summary")).toHaveTextContent("Passes both floors");
  });

  it("does not call a staffed geography not applicable when GM is missing", () => {
    const payload = fixture();
    payload.floors.gm_us = null;
    render(<StaffingGmSection payload={payload} />);
    expect(screen.queryByText("Not applicable — no US resources")).not.toBeInTheDocument();
    expect(screen.getByTestId("staffing-floor-summary")).not.toHaveTextContent("Passes");
  });
});
