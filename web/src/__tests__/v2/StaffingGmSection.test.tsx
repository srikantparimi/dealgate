import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SowConfirmationPayload } from "../../api/client";
import { StaffingGmSection } from "../../pages/v2/sow-studio/confirmation/StaffingGmSection";

function fixture(type = "fixed_price"): SowConfirmationPayload {
  return {
    engagement: { primary: { type, confidence: 1 } },
    staffing: { lines: [{ role: "Engineer", seniority: "Senior", location: "US", hourly_cost: "120.0000", hourly_bill_rate: "0.0000", hours_billable: "80.0000", allocation_pct: "1.0000", provenance: "manual", source_id: null, warning: null, start_date: null, end_date: null }], warnings: [], notes: [], sources: [] },
    gm_model: { id: "gm-1", engagement_type: type, revenue_us: "50000.00", revenue_india: null, resource_line_count: 1 },
    floors: { us_pass: true, india_pass: true, requires_ceo: false, failing: [], gm_us: "0.4240000000", gm_india: null, gm_blended: "0.4240000000" },
  } as unknown as SowConfirmationPayload;
}

describe("S13b Confirm rates", () => {
  it("shows the entered cost and formats hours, allocation, and GM", () => {
    const { container } = render(<StaffingGmSection payload={fixture()} />);
    for (const text of ["Cost /hr", "$120.00", "— fixed price", "80", "100%", "Not applicable — no India resources", "Passes US floor"]) expect(screen.getByText(text)).toBeInTheDocument();
    expect(Array.from(container.querySelectorAll("td, dd, span")).map((node) => node.textContent).join(" ")).not.toMatch(/0\.\d{6,}/);
    expect(container.textContent).not.toContain("0.0000");
  });
  it("shows both entered rates for T&M", () => {
    const payload = fixture("tm");
    payload.staffing.lines[0].hourly_bill_rate = "180.0000";
    render(<StaffingGmSection payload={payload} />);
    expect(screen.getByText("$180.00")).toBeInTheDocument();
    expect(screen.getByText("$120.00")).toBeInTheDocument();
    expect(screen.queryByText("— fixed price")).not.toBeInTheDocument();
  });
});
