import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/commercial";
import * as client from "../../api/client";
import {
  CommercialModelEditor,
  resetCommercialDraftCache,
} from "../../pages/v2/sow-workspace/CommercialModelEditor";
import type { WorkspaceSnapshot } from "../../pages/v2/sow-workspace/readiness";
import { bindCommercialSource } from "../../pages/v2/sow-workspace/commercial-editor/bindings";

function component(
  profile: string,
  pricing: api.CommercialPricing,
): api.CommercialComponent {
  return {
    component_id: "main",
    version: "1",
    source_id: "sow",
    source_version: "v1",
    workstream_id: "Implementation",
    profile,
    profile_version: "1",
    policy_version: "policy",
    source_evidence: ["SOW page 3"],
    service_start: "2026-10-01",
    service_end: "2026-12-31",
    timezone: "UTC",
    currency: "USD",
    billing_cadence: "monthly",
    cost_basis: "loaded",
    costs_confirmed: true,
    costs: [],
    staffing: [],
    pricing,
  };
}
function snap(inputs: api.CommercialComponent): WorkspaceSnapshot {
  return {
    deal: { id: "deal" },
    sow: { id: "v1", sow_id: "sow" },
    gmModel: { id: "gm1", commercial_inputs: inputs },
    approvalPackage: null,
    signedSow: null,
  } as unknown as WorkspaceSnapshot;
}
beforeEach(() => {
  vi.restoreAllMocks();
  resetCommercialDraftCache();
  vi.spyOn(api, "getCommercialDraft").mockResolvedValue({ exists: false });
  vi.spyOn(api, "putCommercialDraft").mockResolvedValue({ exists: true, updated_at: "2026-10-06T00:00:00+00:00" });
  vi.spyOn(api, "deleteCommercialDraft").mockResolvedValue(undefined);
  vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(new Error("no advice"));
  vi.spyOn(api, "getCommercialProposal").mockRejectedValue(new Error("403"));
  vi.spyOn(client, "getMe").mockResolvedValue({
    groups: ["Delivery"],
  } as client.MeResponse);
  vi.spyOn(api, "getCommercialProfiles").mockResolvedValue({
    profiles: [],
    calculation_version: "v1",
    policy: { version: "policy", us_floor: "0.35", india_floor: "0.5" },
  });
  vi.spyOn(api, "previewCommercial").mockResolvedValue({});
});
describe("Commercial pricing profiles", () => {
  it.each(["milestone", "unit", "tm", "calendar_staff_aug", "hybrid"])(
    "keeps signed %s inputs disabled for Delivery",
    async (profile) => {
      const snapshot = snap(component(profile, {}));
      snapshot.approvalPackage = {
        sow_version_id: "v1",
        status: "released",
      } as WorkspaceSnapshot["approvalPackage"];
      await act(async () => {
        render(<CommercialModelEditor snap={snapshot} />);
      });
      expect(screen.getByLabelText("Pricing profile")).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "Save" }),
      ).toBeDisabled();
      expect(
        screen.getByText(
          "Signed financial basis. Changes require a separate amendment version.",
        ),
      ).toBeInTheDocument();
    },
  );
  it("binds a new hybrid revision to the current source and policy without mutating its financial inputs", () => {
    const child = component("unit", {
      rate: "987.654321",
      unit: "point",
      quantities: [],
    });
    const parent = component("hybrid", {
      components: [child],
      fx_rates: [
        {
          currency: "INR",
          rate: "0.012345",
          version: "fx-v1",
          as_of: "2026-10-01",
        },
      ],
    });
    const bound = bindCommercialSource(parent, {
      source_id: "sow-new",
      source_version: "sow-version-new",
      policy_version: "policy-new",
    });
    expect(bound.pricing!.components![0]).toEqual({
      ...child,
      source_id: "sow-new",
      source_version: "sow-version-new",
      policy_version: "policy-new",
    });
    expect(bound.pricing!.fx_rates).toEqual(parent.pricing!.fx_rates);
    expect(parent.source_id).toBe("sow");
    expect(child.policy_version).toBe("policy");
  });
  it("edits a staffing cost while preserving the stored calendar evidence", async () => {
    const inputs = component("calendar_staff_aug", {
      rates: [
        {
          assignment_id: "assignment",
          basis: "hourly",
          rate: "100",
          version: "rate1",
          hours_per_day: null,
          proration: null,
        },
      ],
    });
    inputs.staffing = [
      {
        assignment_id: "assignment",
        source_id: "sow",
        source_version: "v1",
        component_id: "main",
        profile_version: "1",
        policy_version: "policy",
        role: "Engineer",
        location: "US",
        timezone: "UTC",
        currency: "USD",
        quantity: 10,
        allocation: "0.5",
        calendar: {
          calendar_id: "client-calendar",
          version: "2",
          timezone: "UTC",
          coverage_start: "2026-10-01",
          coverage_end: "2026-12-31",
          week: Array.from({ length: 7 }, (_, i) => ({
            scheduled: i < 5 ? "8" : "0",
            billable: i < 5 ? "8" : "0",
            paid: i < 5 ? "8" : "0",
          })),
          overrides: [
            {
              day: "2026-11-26",
              hours: { scheduled: "0", billable: "0", paid: "8" },
              reason: "Paid client holiday",
            },
          ],
        },
        bill_rate: "100",
        cost_rate: "60",
        rate_version: "rate1",
        cost_version: "cost1",
        start: "2026-10-01",
        end: "2026-12-31",
      },
    ];
    render(<CommercialModelEditor snap={snap(inputs)} />);
    fireEvent.change(screen.getByLabelText("Cost per hour 1"), {
      target: { value: "61.000001" },
    });
    await waitFor(() =>
      expect(api.previewCommercial).toHaveBeenCalledWith(
        expect.objectContaining({
          staffing: [expect.objectContaining({
            assignment_id: "assignment",
            cost_rate: "61.000001",
            cost_version: "manual",
            calendar: inputs.staffing[0].calendar,
          })],
          pricing: inputs.pricing,
        }),
      ), { timeout: 3000 },
    );
  });
  it("edits hybrid child rates and shared-cost weights without flattening component evidence", async () => {
    const child = {
      ...component("unit", {
        rate: "125",
        unit: "point",
        contractual_basis: "Accepted points",
        quantities: [
          {
            source_id: "points",
            month: "2026-11-01",
            location: "US",
            quantity: "100",
          },
        ],
      }),
      component_id: "child",
      source_evidence: ["SOW page 4"],
    };
    const inputs = component("hybrid", {
      components: [child],
      shared_cost_allocations: [
        { source_id: "shared", component_id: "child", weight: "1" },
      ],
      allocation_basis: "Confirmed shared delivery",
      minor_unit: "0.01",
      fx_rates: [],
    });
    inputs.costs = [
      {
        source_id: "shared",
        month: "2026-11-01",
        location: "US",
        amount: "1000",
      },
    ];
    render(<CommercialModelEditor snap={snap(inputs)} />);
    fireEvent.change(
      within(
        screen.getByRole("region", { name: "Component 1" }),
      ).getByLabelText("Unit rate"),
      { target: { value: "130.25" } },
    );
    fireEvent.change(screen.getByLabelText("Shared cost weight 1"), {
      target: { value: "2" },
    });
    await waitFor(() =>
      expect(api.previewCommercial).toHaveBeenCalledWith(
        expect.objectContaining({
          costs: inputs.costs,
          pricing: {
            ...inputs.pricing,
            components: [
              { ...child, pricing: { ...child.pricing, rate: "130.25" } },
            ],
            shared_cost_allocations: [
              { source_id: "shared", component_id: "child", weight: "2" },
            ],
          },
        }),
      ), { timeout: 3000 },
    );
  });
  it("edits milestone amount and acceptance while preserving accounting references", async () => {
    const inputs = component("milestone", {
      milestones: [
        {
          milestone_id: "m1",
          planned_date: "2026-11-01",
          location: "US",
          amount: "42000.01",
          acceptance_conditions: "Client acceptance",
          approved_invoice_ref: "invoice-1",
          recognized_revenue_ref: "recognized-1",
        },
      ],
    });
    render(<CommercialModelEditor snap={snap(inputs)} />);
    fireEvent.change(screen.getByLabelText("Milestone amount 1"), {
      target: { value: "43000.02" },
    });
    await waitFor(() =>
      expect(api.previewCommercial).toHaveBeenCalledWith(
        expect.objectContaining({
          source_evidence: inputs.source_evidence,
          pricing: {
            milestones: [
              { ...inputs.pricing!.milestones![0], amount: "43000.02" },
            ],
          },
        }),
      ), { timeout: 3000 },
    );
  });
  it("edits unit/story point rates without calculating revenue in the browser", async () => {
    const inputs = component("unit", {
      rate: "123.456789",
      unit: "story point",
      contractual_basis: "Accepted points",
      quantities: [
        {
          source_id: "q1",
          month: "2026-11-01",
          location: "India",
          quantity: "12.25",
        },
      ],
    });
    render(<CommercialModelEditor snap={snap(inputs)} />);
    fireEvent.change(screen.getByLabelText("Unit rate"), {
      target: { value: "124.000001" },
    });
    await waitFor(() =>
      expect(api.previewCommercial).toHaveBeenCalledWith(
        expect.objectContaining({
          pricing: { ...inputs.pricing, rate: "124.000001" },
        }),
      ), { timeout: 3000 },
    );
  });
  it("edits T&M cap and approved usage without replacing estimates", async () => {
    const inputs = component("tm", {
      rate: "200",
      unit: "hour",
      cap: "20000",
      minimum: "2000",
      limit_allocation_basis: "service month",
      minor_unit: "0.01",
      calendar_estimates: false,
      estimates: [
        {
          source_id: "estimate",
          month: "2026-11-01",
          location: "US",
          quantity: "100",
        },
      ],
      approved_usage: [
        {
          source_id: "actual",
          month: "2026-11-01",
          location: "US",
          quantity: "80",
        },
      ],
    });
    render(<CommercialModelEditor snap={snap(inputs)} />);
    fireEvent.change(screen.getByLabelText("Contract cap"), {
      target: { value: "21000.05" },
    });
    fireEvent.change(screen.getByLabelText("Approved quantity 1"), {
      target: { value: "81.25" },
    });
    await waitFor(() =>
      expect(api.previewCommercial).toHaveBeenCalledWith(
        expect.objectContaining({
          pricing: {
            ...inputs.pricing,
            cap: "21000.05",
            approved_usage: [
              { ...inputs.pricing!.approved_usage![0], quantity: "81.25" },
            ],
          },
        }),
      ), { timeout: 3000 },
    );
  });
  it("requires confirmation before replacing incompatible pricing terms", async () => {
    render(
      <CommercialModelEditor
        snap={snap(
          component("unit", {
            rate: "100",
            unit: "point",
            quantities: [],
            contractual_basis: "Accepted points",
          }),
        )}
      />,
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Pricing profile")).toBeEnabled(),
    );
    fireEvent.change(screen.getByLabelText("Pricing profile"), {
      target: { value: "milestone" },
    });
    expect(screen.getByLabelText("Unit rate")).toHaveValue("100");
    fireEvent.click(screen.getByRole("button", { name: "Keep current model" }));
    expect(screen.getByLabelText("Unit rate")).toHaveValue("100");
    fireEvent.change(screen.getByLabelText("Pricing profile"), {
      target: { value: "milestone" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Replace pricing terms" }),
    );
    expect(
      screen.getByRole("button", { name: "Add milestone" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Unit rate")).not.toBeInTheDocument();
  });
});
