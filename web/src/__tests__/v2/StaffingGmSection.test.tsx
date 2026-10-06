import { fireEvent, render, screen } from "@testing-library/react";
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

/** S22 root-cause fix · the Confirm page reads the server-persisted
 * Staffing & GM draft instead of "No staffing lines yet / GM
 * unavailable" when no resource lines exist. */
import { vi, beforeEach } from "vitest";
import { waitFor } from "@testing-library/react";
import * as commercialApi from "../../api/commercial";
import * as client from "../../api/client";

describe("Commercial draft bridge", () => {
  beforeEach(() => vi.restoreAllMocks());

  function emptyFixture(): SowConfirmationPayload {
    const payload = fixture();
    payload.staffing.lines = [];
    (payload as unknown as { gm_model: null }).gm_model = null;
    (payload as unknown as { floors: object }).floors = {};
    return payload;
  }

  it("shows the draft team and its provisional GM when no lines are saved", async () => {
    vi.spyOn(client, "getSowStaffing").mockRejectedValue(new Error("none"));
    vi.spyOn(commercialApi, "getCommercialDraft").mockResolvedValue({
      exists: true,
      inputs: {
        component_id: "c1", version: "1", source_id: "sow-a",
        source_version: "version-a", workstream_id: "w", profile: "fixed_assignment",
        profile_version: "1", policy_version: "", source_evidence: [],
        service_start: "2026-10-01", service_end: "2026-11-18",
        timezone: null, currency: "USD", billing_cadence: null,
        cost_basis: null, costs_confirmed: false, costs: [],
        staffing: [{
          assignment_id: "a1", source_id: "sow-a", source_version: "version-a",
          component_id: "c1", profile_version: "1", policy_version: "",
          role: "Offshore consultant", location: "India", timezone: "Asia/Kolkata",
          currency: "USD", quantity: 2, allocation: "1", calendar: null,
          bill_rate: null, cost_rate: "30", rate_version: null,
          cost_version: "rate-card", start: "2026-10-01", end: "2026-11-18",
          cost_rate_basis: "hourly", cost_proration: null,
        }],
        pricing: { total_fee: "75400", allocations: [], allocation_basis: "even", minor_unit: "0.01" },
      } as unknown as commercialApi.CommercialComponent,
      sow_version_id: "version-a",
      updated_at: "2026-10-06T01:00:00+00:00",
    });
    vi.spyOn(commercialApi, "getCommercialProfiles").mockResolvedValue({
      profiles: [], calculation_version: "v1",
      policy: { version: "policy", us_floor: "0.35", india_floor: "0.5" },
    });
    vi.spyOn(commercialApi, "previewCommercial").mockResolvedValue({
      computed: {
        complete: true, gm_us: null, gm_india: "0.722",
        policy: { requires_ceo: false, india_pass: true, us_pass: null },
      } as never,
    });
    render(<StaffingGmSection payload={emptyFixture()} opportunityId="deal-a" />);
    const table = await screen.findByTestId("draft-staffing");
    expect(table).toHaveTextContent("Offshore consultant");
    expect(table).toHaveTextContent("India");
    expect(screen.getByText(/working draft/)).toBeInTheDocument();
    expect(screen.queryByText("No staffing lines yet.")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(commercialApi.previewCommercial).toHaveBeenCalled(),
    );
  });

  it("keeps the honest empty state when no draft exists", async () => {
    vi.spyOn(client, "getSowStaffing").mockRejectedValue(new Error("none"));
    vi.spyOn(commercialApi, "getCommercialDraft").mockResolvedValue({ exists: false });
    vi.spyOn(commercialApi, "getCommercialProfiles").mockResolvedValue({
      profiles: [], calculation_version: "v1",
      policy: { version: "policy", us_floor: "0.35", india_floor: "0.5" },
    });
    render(<StaffingGmSection payload={emptyFixture()} opportunityId="deal-a" />);
    await waitFor(() =>
      expect(commercialApi.getCommercialDraft).toHaveBeenCalled(),
    );
    expect(screen.getByText("No staffing lines yet.")).toBeInTheDocument();
  });
});

describe("Draft GM gates on the Confirm page (round 3)", () => {
  function draftInputs(costsConfirmed: boolean) {
    return {
      component_id: "c1", version: "1", source_id: "sow-a",
      source_version: "version-a", workstream_id: "delivery",
      profile: "fixed_assignment", profile_version: "1", policy_version: "",
      source_evidence: [], service_start: "2026-10-01",
      service_end: "2026-12-01", timezone: "America/Los_Angeles",
      currency: "USD", billing_cadence: null, cost_basis: null,
      costs_confirmed: costsConfirmed, costs: [],
      staffing: [{
        assignment_id: "a1", source_id: "sow-a", source_version: "version-a",
        component_id: "c1", profile_version: "1", policy_version: "",
        role: "Offshore consultant", location: "India", timezone: "Asia/Kolkata",
        currency: "USD", quantity: 2, allocation: "1", calendar: null,
        bill_rate: null, cost_rate: "30", rate_version: null,
        cost_version: "rate-card", start: "2026-10-01", end: "2026-12-01",
        cost_rate_basis: "hourly", cost_proration: null,
      }],
      pricing: { total_fee: "75400", allocations: [{ month: "2026-10-01", location: "India", weight: "1" }], allocation_basis: "even", minor_unit: "0.01" },
    } as unknown as commercialApi.CommercialComponent;
  }
  function emptyPayload(): SowConfirmationPayload {
    const payload = fixture();
    payload.staffing.lines = [];
    (payload as unknown as { gm_model: null }).gm_model = null;
    (payload as unknown as { floors: object }).floors = {};
    return payload;
  }
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, "getSowStaffing").mockRejectedValue(new Error("none"));
    vi.spyOn(commercialApi, "getCommercialProfiles").mockResolvedValue({
      profiles: [], calculation_version: "v1",
      policy: { version: "policy", us_floor: "0.35", india_floor: "0.5" },
    });
  });

  it("explains exactly what GM is waiting on, and the attestation tick writes the draft", async () => {
    vi.spyOn(commercialApi, "getCommercialDraft").mockResolvedValue({
      exists: true, inputs: draftInputs(false),
      sow_version_id: "version-a", updated_at: "2026-10-06T01:00:00+00:00",
    });
    vi.spyOn(commercialApi, "previewCommercial").mockResolvedValue({
      computed: { complete: false, gm_us: null, gm_india: null, policy: {} } as never,
      commercial_snapshot: {
        schedule: {
          rows: [], status: "incomplete",
          missing: [{ field: "costs_confirmed", reason: "cost plan has not been confirmed" }],
        },
      } as never,
    });
    const put = vi.spyOn(commercialApi, "putCommercialDraft").mockResolvedValue({
      exists: true, updated_at: "2026-10-06T02:00:00+00:00",
    });
    render(<StaffingGmSection payload={emptyPayload()} opportunityId="deal-a" />);
    const missing = await screen.findByTestId("draft-gm-missing");
    expect(missing).toHaveTextContent("cost plan has not been confirmed");
    fireEvent.click(screen.getByTestId("draft-attest-costs"));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    const body = put.mock.calls[0][1];
    expect(body.inputs.costs_confirmed).toBe(true);
    expect(body.expected_updated_at).toBe("2026-10-06T01:00:00+00:00");
  });

  it("uses the draft's delivery locations for floor applicability — no 'no India resources' lie", async () => {
    vi.spyOn(commercialApi, "getCommercialDraft").mockResolvedValue({
      exists: true, inputs: draftInputs(true),
      sow_version_id: "version-a", updated_at: "2026-10-06T01:00:00+00:00",
    });
    vi.spyOn(commercialApi, "previewCommercial").mockResolvedValue({
      computed: {
        complete: true, gm_us: null, gm_india: "0.7220",
        gm_blended: "0.7220",
        policy: { requires_ceo: false, india_pass: true, us_pass: null },
        finance_summary: {
          revenue: "75400.00", labor_cost: "21000.00", direct_cost: "0.00",
          total_delivery_cost: "21000.00", gross_profit: "54400.00",
          labor_pct: "0.2785", direct_pct: "0.0000", total_cost_pct: "0.2785",
          pass_through: "0",
        },
      } as never,
      commercial_snapshot: { schedule: { rows: [], status: "ok", missing: [] } } as never,
    });
    render(<StaffingGmSection payload={emptyPayload()} opportunityId="deal-a" />);
    await screen.findByTestId("draft-staffing");
    await waitFor(() => {
      expect(screen.getAllByText("72.2%").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("$75,400")).toBeInTheDocument(); // contract price
    expect(screen.getByText("$54,400")).toBeInTheDocument(); // gross profit
    expect(screen.queryByText(/no India resources/)).not.toBeInTheDocument();
    expect(screen.getByText(/Not applicable — no US resources/)).toBeInTheDocument();
  });
});
