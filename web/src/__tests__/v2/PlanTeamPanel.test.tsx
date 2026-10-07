/**
 * S22 redesign · AI proposal card: independent scope demand first, an
 * explicit blocked state when the fee is missing, a loud delivery
 * caution with four resolution actions, and compare → apply → undo
 * that never silently changes the draft.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/commercial";
import { PlanTeamPanel } from "../../pages/v2/sow-workspace/commercial-editor/PlanTeamPanel";

const baseInputs = {
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
      min_onshore_fte: "0", onshore_cost_per_hour: "95",
      offshore_cost_per_hour: "30", rates_provenance: "looked_up",
    },
    estimate: {
      required_fte: "2.5", duration_weeks: "7",
      roles: [{
        role: "ServiceNow Consultant", fte: "2", location_hint: null,
        evidence: "2 full-time", skills: ["ServiceNow"], seniority: null,
        phase: null, people: 2, allocation: "1", basis: "stated",
      }],
      rationale: "team statement",
      evidence: ["Team Size: 3 consultants (2 full-time, 1 half-time)"],
      unknowns: ["No shift coverage stated"],
      coverage: null,
      provenance: "extracted",
    },
    affordability: "calculated",
    blocked_reasons: [],
    suggested: { onshore_fte: "1", offshore_fte: "1.5", cost: "39200", gm: "0.4801" },
    feasible: true,
    max_fte_at_target: "5",
    caution: null,
    warnings: [],
    sow_version_id: "version-a",
    ...overrides,
  };
}

/** The editor owns advice + component state; mirror that here. */
function Harness({
  inputs = baseInputs,
  onApply,
  onResolve,
}: {
  inputs?: api.CommercialComponent;
  onApply?: (next: api.CommercialComponent) => void;
  onResolve?: (action: string) => void;
}) {
  const [component, setComponent] = useState(inputs);
  const [current, setCurrent] = useState<api.StaffingAdvice | null>(null);
  return (
    <PlanTeamPanel
      opportunityId="deal-a"
      inputs={component}
      advice={current}
      onAdvice={setCurrent}
      onApply={(next) => {
        setComponent(next);
        onApply?.(next);
      }}
      onResolve={onResolve}
    />
  );
}

beforeEach(() => vi.restoreAllMocks());

describe("PlanTeamPanel", () => {
  it("realigns only provisional fixed-fee geography to the applied team's delivery location", async () => {
    const onApply = vi.fn();
    vi.spyOn(api, "getStaffingAdvice").mockResolvedValue(advice({
      suggested: {
        onshore_fte: "0",
        offshore_fte: "1.5",
        cost: "12000",
        gm: "0.5",
      },
    }));
    render(<Harness
      onApply={onApply}
      inputs={{
        ...baseInputs,
        pricing: {
          ...baseInputs.pricing,
          allocation_basis: "even service months (proposed)",
          allocations: [
            { month: "2026-10-01", location: "US", weight: "1" },
          ],
        },
      }}
    />);
    await screen.findByTestId("plan-team-review");
    fireEvent.click(screen.getByTestId("plan-team-review"));
    fireEvent.click(await screen.findByTestId("plan-team-apply"));
    await waitFor(() => expect(onApply).toHaveBeenCalled());
    const applied = onApply.mock.calls.at(-1)?.[0] as api.CommercialComponent;
    expect(applied.staffing).toHaveLength(2);
    expect(applied.staffing.every((row) => row.location === "India")).toBe(true);
    expect(applied.pricing?.allocations).toEqual([
      { month: "2026-10-01", location: "India", weight: "1" },
    ]);
  });
  it("shows the demand estimate with role shapes, quotes and the feasible mix", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockResolvedValue(advice());
    render(<Harness />);
    fireEvent.click(screen.getByTestId("plan-team-advise"));
    await screen.findByTestId("plan-team-result");
    expect(screen.getByText(/2.5 FTE/)).toBeInTheDocument();
    expect(screen.getByTestId("plan-team-roles")).toHaveTextContent(
      "2 × 100% ServiceNow Consultant",
    );
    expect(screen.getByTestId("plan-team-roles")).toHaveTextContent("stated in SOW");
    expect(screen.getByText(/Unknown: No shift coverage stated/)).toBeInTheDocument();
    expect(screen.getByTestId("plan-team-mix")).toHaveTextContent(
      "1 onshore + 1.5 offshore",
    );
    expect(screen.getByTestId("plan-team-mix")).toHaveTextContent("48.01%");
    expect(screen.queryByTestId("plan-team-caution")).not.toBeInTheDocument();
  });

  it("missing fee is an explicit blocked state — demand still shows", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockResolvedValue(
      advice({
        affordability: "blocked",
        blocked_reasons: ["No contract fee — enter the fee to assess affordability"],
        suggested: null,
        feasible: false,
        max_fte_at_target: null,
        inputs: { ...advice().inputs, revenue: null },
      }),
    );
    render(<Harness />);
    fireEvent.click(screen.getByTestId("plan-team-advise"));
    await screen.findByTestId("plan-team-result");
    expect(screen.getByText(/2.5 FTE/)).toBeInTheDocument();
    expect(screen.getByTestId("plan-team-blocked")).toHaveTextContent("No contract fee");
    expect(screen.queryByTestId("plan-team-mix")).not.toBeInTheDocument();
  });

  it("raises the delivery caution with four resolution actions; exception is labeled as not curing the gap", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockResolvedValue(
      advice({
        feasible: false,
        caution:
          "Scope needs ~6 FTE but the fee supports at most 4 FTE at the 35% GM target — delivery risk",
      }),
    );
    const onResolve = vi.fn();
    render(<Harness onResolve={onResolve} />);
    fireEvent.click(screen.getByTestId("plan-team-advise"));
    const caution = await screen.findByTestId("plan-team-caution");
    expect(caution).toHaveTextContent("delivery risk");
    expect(caution).toHaveTextContent("does not add people or cure a delivery gap");
    fireEvent.click(screen.getByTestId("resolve-fee"));
    expect(onResolve).toHaveBeenCalledWith("fee");
    for (const id of ["resolve-scope", "resolve-term", "resolve-exception"]) {
      expect(screen.getByTestId(id)).toBeInTheDocument();
    }
  });

  it("applies the mix only after review, and undo restores the prior rows", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockResolvedValue(advice());
    const onApply = vi.fn();
    render(<Harness onApply={onApply} />);
    fireEvent.click(screen.getByTestId("plan-team-advise"));
    await screen.findByTestId("plan-team-review");
    expect(screen.queryByTestId("plan-team-apply")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("plan-team-review"));
    await screen.findByTestId("plan-team-compare");
    fireEvent.click(screen.getByTestId("plan-team-apply"));
    await waitFor(() => expect(onApply).toHaveBeenCalledTimes(1));
    const next = onApply.mock.calls[0][0] as api.CommercialComponent;
    expect(next.staffing).toHaveLength(3); // 1 US full + 1 India full + 1 India part
    const part = next.staffing.find((a) => a.allocation === "0.5");
    expect(part).toBeDefined();
    expect(part!.location).toBe("India");
    expect(part!.cost_rate).toBe("30");
    expect(next.staffing[0].cost_rate_basis).toBe("hourly");
    expect(next.costs_confirmed).toBe(false); // apply never attests costs
    // Undo restores the pre-apply team (empty here).
    fireEvent.click(screen.getByTestId("plan-team-undo"));
    await waitFor(() => expect(onApply).toHaveBeenCalledTimes(2));
    expect((onApply.mock.calls[1][0] as api.CommercialComponent).staffing).toHaveLength(0);
  });

  it("requests the scope assessment automatically for an empty draft", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockResolvedValue(advice());
    render(<Harness />);
    // No click: the independent scope estimate arrives on its own.
    await screen.findByTestId("plan-team-result");
    expect(screen.getByTestId("plan-team-mix")).toHaveTextContent("1 onshore");
    // One auto-run, not one per render/keystroke.
    expect(api.getStaffingAdvice).toHaveBeenCalledTimes(1);
  });
});
