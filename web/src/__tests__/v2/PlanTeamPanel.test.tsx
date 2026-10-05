/**
 * S22 · Plan-the-team panel: advice renders the mix, the caution is loud,
 * and Apply fills Calendar staffing through the editor's own state.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/commercial";
import { PlanTeamPanel } from "../../pages/v2/sow-workspace/commercial-editor/PlanTeamPanel";

const inputs = {
  component_id: "c1",
  version: "1",
  source_id: "sow-a",
  source_version: "version-a",
  workstream_id: "delivery",
  profile: "fixed_assignment",
  profile_version: "1",
  policy_version: "policy-active",
  source_evidence: ["sow-version:version-a"],
  service_start: "2026-10-01",
  service_end: "2026-11-18",
  timezone: "America/Los_Angeles",
  currency: "USD",
  billing_cadence: null,
  cost_basis: null,
  costs_confirmed: false,
  costs: [],
  staffing: [],
  pricing: { total_fee: "75400", allocations: [], allocation_basis: null, minor_unit: "0.01" },
} as unknown as api.CommercialComponent;

function advice(overrides: Partial<api.StaffingAdvice> = {}): api.StaffingAdvice {
  return {
    inputs: {
      revenue: "75400", weeks: "7", target_gm: "0.35",
      target_gm_provenance: "manual", required_fte: "2.5",
      min_onshore_fte: "1", onshore_cost_per_hour: "95",
      offshore_cost_per_hour: "30", rates_provenance: "looked_up",
    },
    estimate: {
      required_fte: "2.5", duration_weeks: "7", roles: [],
      rationale: "team statement", provenance: "extracted",
      evidence: ["Team Size: 3 consultants (2 full-time, 1 half-time)"],
    },
    suggested: { onshore_fte: "1", offshore_fte: "1.5", cost: "39200", gm: "0.4801" },
    feasible: true,
    max_fte_at_target: "5",
    caution: null,
    warnings: [],
    sow_version_id: "version-a",
    ...overrides,
  };
}

beforeEach(() => vi.restoreAllMocks());

describe("PlanTeamPanel", () => {
  it("shows the estimate with quotes and the feasible mix", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockResolvedValue(advice());
    render(<PlanTeamPanel opportunityId="deal-a" inputs={inputs} onApply={() => {}} />);
    fireEvent.click(screen.getByTestId("plan-team-advise"));
    await screen.findByTestId("plan-team-result");
    expect(screen.getByText(/2.5 FTE/)).toBeInTheDocument();
    expect(screen.getByText(/2 full-time, 1 half-time/)).toBeInTheDocument();
    expect(screen.getByTestId("plan-team-mix")).toHaveTextContent(
      "1 onshore + 1.5 offshore",
    );
    expect(screen.getByTestId("plan-team-mix")).toHaveTextContent("48.0%");
    expect(screen.queryByTestId("plan-team-caution")).not.toBeInTheDocument();
  });

  it("raises the delivery caution loudly when infeasible", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockResolvedValue(
      advice({
        feasible: false,
        caution:
          "Scope needs ~6 FTE but the fee supports at most 4 FTE at the 35% GM target — delivery risk",
      }),
    );
    render(<PlanTeamPanel opportunityId="deal-a" inputs={inputs} onApply={() => {}} />);
    fireEvent.click(screen.getByTestId("plan-team-advise"));
    const caution = await screen.findByTestId("plan-team-caution");
    expect(caution).toHaveTextContent("delivery risk");
  });

  it("applies the mix as calendar assignments with utilization intact", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockResolvedValue(advice());
    const onApply = vi.fn();
    render(<PlanTeamPanel opportunityId="deal-a" inputs={inputs} onApply={onApply} />);
    fireEvent.click(screen.getByTestId("plan-team-advise"));
    await screen.findByTestId("plan-team-apply");
    fireEvent.click(screen.getByTestId("plan-team-apply"));
    await waitFor(() => expect(onApply).toHaveBeenCalledTimes(1));
    const next = onApply.mock.calls[0][0] as api.CommercialComponent;
    expect(next.staffing).toHaveLength(3); // 1 US full + 1 India full + 1 India half
    const half = next.staffing.find((a) => a.allocation === "0.5");
    expect(half).toBeDefined();
    expect(half!.location).toBe("India");
    expect(half!.cost_rate).toBe("30");
    expect(next.staffing[0].cost_rate_basis).toBe("hourly");
  });
});
