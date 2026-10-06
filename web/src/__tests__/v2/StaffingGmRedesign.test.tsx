/**
 * S22 redesign · four-section Staffing & GM plan: exact percent
 * round-trips, the Scope/Budget/Planned summary that a green margin
 * cannot hide behind, draft survival across unmount, and row
 * duplication that visibly changes totals.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/commercial";
import * as client from "../../api/client";
import {
  CommercialModelEditor,
  resetCommercialDraftCache,
} from "../../pages/v2/sow-workspace/CommercialModelEditor";
import {
  fractionToPercent,
  percentToFraction,
} from "../../pages/v2/sow-workspace/format";
import type { WorkspaceSnapshot } from "../../pages/v2/sow-workspace/readiness";

describe("percent round-trip (string shift, no floats)", () => {
  it("shifts exactly in both directions", () => {
    expect(fractionToPercent("0.3333")).toBe("33.33");
    expect(percentToFraction("33.33")).toBe("0.3333");
    expect(fractionToPercent("0.5")).toBe("50");
    expect(percentToFraction("50")).toBe("0.5");
    expect(fractionToPercent("1")).toBe("100");
    expect(percentToFraction("100")).toBe("1");
    expect(fractionToPercent("0.000001")).toBe("0.0001");
    expect(percentToFraction("0.0001")).toBe("0.000001");
    expect(fractionToPercent("1.25")).toBe("125");
  });
  it("passes through in-progress or invalid input unchanged", () => {
    expect(percentToFraction("")).toBe("");
    expect(percentToFraction("abc")).toBe("abc");
    expect(fractionToPercent(null)).toBe("");
    // A value that is not yet a number is not mangled mid-keystroke.
    expect(percentToFraction("-")).toBe("-");
  });
  it("round-trips every schema fraction it produces", () => {
    for (const fraction of ["0.3333", "0.5", "0.25", "0.125", "1", "0.07"]) {
      expect(percentToFraction(fractionToPercent(fraction))).toBe(fraction);
    }
  });
});

const staffedInputs = {
  component_id: "c1",
  version: "1",
  source_id: "sow-a",
  source_version: "version-a",
  workstream_id: "delivery",
  profile: "fixed_assignment",
  profile_version: "1",
  policy_version: "policy",
  source_evidence: [],
  service_start: "2026-10-01",
  service_end: "2026-11-18",
  timezone: null,
  currency: "USD",
  billing_cadence: null,
  cost_basis: null,
  costs_confirmed: false,
  costs: [],
  staffing: [
    {
      assignment_id: "row-1",
      source_id: "sow-a",
      source_version: "version-a",
      component_id: "c1",
      profile_version: "1",
      policy_version: "policy",
      role: "Consultant",
      location: "India",
      timezone: "Asia/Kolkata",
      currency: "USD",
      quantity: 2,
      allocation: "0.5",
      calendar: null,
      bill_rate: null,
      cost_rate: "30",
      rate_version: null,
      cost_version: "rate-card",
      start: "2026-10-01",
      end: "2026-11-18",
      cost_rate_basis: "hourly",
      cost_proration: null,
    },
  ],
  pricing: {
    total_fee: "75400",
    allocations: [{ month: "2026-10-01", location: "US", weight: "0.3333" }],
    allocation_basis: "even months",
    minor_unit: "0.01",
  },
} as unknown as api.CommercialComponent;

function snap(): WorkspaceSnapshot {
  return {
    deal: { id: "deal-a" },
    sow: { id: "version-a", sow_id: "sow-a", extracted_fields: {} },
    gmModel: { id: "gm-1", commercial_inputs: structuredClone(staffedInputs) },
    approvalPackage: null,
    signedSow: null,
  } as unknown as WorkspaceSnapshot;
}

function goodAdvice(): api.StaffingAdvice {
  return {
    inputs: {
      revenue: "75400", weeks: "7", target_gm: "0.35",
      target_gm_provenance: "manual", required_fte: "2.5",
      min_onshore_fte: "0", onshore_cost_per_hour: "95",
      offshore_cost_per_hour: "30", rates_provenance: "looked_up",
    },
    estimate: {
      required_fte: "2.5", duration_weeks: "7", roles: [],
      rationale: "", evidence: ["Team Size: 3 consultants"],
      unknowns: [], coverage: null, provenance: "extracted",
    },
    affordability: "calculated",
    blocked_reasons: [],
    suggested: { onshore_fte: "0", offshore_fte: "2.5", cost: "21000", gm: "0.722" },
    feasible: true,
    max_fte_at_target: "5",
    caution: null,
    warnings: [],
    sow_version_id: "version-a",
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  resetCommercialDraftCache();
  vi.spyOn(client, "getTermAssist").mockResolvedValue({ available: false });
  vi.spyOn(client, "getMe").mockResolvedValue({
    groups: ["Delivery"],
  } as client.MeResponse);
  vi.spyOn(api, "getCommercialProfiles").mockResolvedValue({
    profiles: [],
    calculation_version: "v1",
    policy: { version: "policy", us_floor: "0.35", india_floor: "0.5" },
  });
  vi.spyOn(api, "getCommercialProposal").mockRejectedValue(new Error("403"));
  vi.spyOn(api, "previewCommercial").mockResolvedValue({});
});

describe("Staffing & GM four-section plan", () => {
  it("renders all four sections, one summary, and no second readiness panel", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(new Error("none"));
    render(<CommercialModelEditor snap={snap()} />);
    for (const id of ["contract", "team", "monthly", "review"]) {
      expect(screen.getByTestId(`sgm-section-${id}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("sgm-summary")).toBeInTheDocument();
    // The single readiness panel lives in the workspace shell, not here.
    expect(screen.queryByText("Readiness")).not.toBeInTheDocument();
  });

  it("summary shows Unknown (never zero) without an estimate, and exact planned effort", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(new Error("none"));
    render(<CommercialModelEditor snap={snap()} />);
    expect(screen.getByTestId("summary-scope")).toHaveTextContent("Unknown");
    expect(screen.getByTestId("summary-budget")).toHaveTextContent("Unknown");
    // 2 people × 50% = 1 FTE — people and FTE both named.
    expect(screen.getByTestId("summary-planned")).toHaveTextContent("2 people · 1 FTE");
  });

  it("a green margin cannot hide understaffing: the gap alert shows with a feasible-looking mix", async () => {
    // Scope needs 2.5; planned is 1 FTE; GM in advice is a healthy 72.2%.
    vi.spyOn(api, "getStaffingAdvice").mockResolvedValue(goodAdvice());
    const snapshot = snap();
    render(<CommercialModelEditor snap={snapshot} />);
    // Deliberate regeneration (staffing is non-empty so no auto-run).
    fireEvent.click(await screen.findByTestId("plan-team-advise"));
    await screen.findByTestId("plan-team-result");
    const alert = await screen.findByTestId("summary-understaffed");
    expect(alert).toHaveTextContent("1 of the ~2.5 FTE");
    expect(alert).toHaveTextContent("passing margin does not make this plan delivery-ready");
  });

  it("duplicate creates an editable copy and totals change visibly", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(new Error("none"));
    render(<CommercialModelEditor snap={snap()} />);
    expect(screen.getByTestId("summary-planned")).toHaveTextContent("2 people · 1 FTE");
    fireEvent.click(screen.getByLabelText("Duplicate role 1"));
    await waitFor(() =>
      expect(screen.getByTestId("summary-planned")).toHaveTextContent("4 people · 2 FTE"),
    );
    const roles = screen.getAllByLabelText("Role");
    expect(roles).toHaveLength(2);
    expect(roles[1]).toHaveValue("Consultant (copy)");
  });

  it("monthly share edits in percent keep the exact fraction in the save payload", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(new Error("none"));
    const preview = vi.spyOn(api, "previewCommercial").mockResolvedValue({});
    render(<CommercialModelEditor snap={snap()} />);
    const share = screen.getByLabelText("Share of contract (%) 1");
    expect(share).toHaveValue("33.33"); // stored 0.3333 shown as percent
    fireEvent.change(share, { target: { value: "50" } });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Preview" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    await waitFor(() =>
      expect(preview).toHaveBeenCalledWith(
        expect.objectContaining({
          pricing: expect.objectContaining({
            allocations: [
              { month: "2026-10-01", location: "US", weight: "0.5" },
            ],
          }),
        }),
      ),
    );
  });

  it("derives the contract end date from the SOW's stated duration on click (never silently)", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(new Error("none"));
    vi.spyOn(client, "getTermAssist").mockResolvedValue({
      available: true,
      weeks: 7,
      source_field: "milestones",
      quote: "Week 7 — Roadmap & Executive Readout",
      start: "2026-10-01",
      suggested_end: "2026-11-18",
    });
    const snapshot = snap();
    const inputs = snapshot.gmModel!.commercial_inputs!;
    inputs.service_start = "2026-10-01";
    inputs.service_end = null;
    render(<CommercialModelEditor snap={snapshot} />);
    const apply = await screen.findByTestId("editor-term-assist-apply");
    expect(apply).toHaveTextContent("Use 2026-11-18 (start + 7 weeks)");
    expect(screen.getByTestId("editor-term-assist")).toHaveTextContent(
      "Week 7 — Roadmap & Executive Readout",
    );
    // Not applied until the human clicks.
    expect(screen.getByLabelText("Contract end")).toHaveValue("");
    fireEvent.click(apply);
    expect(screen.getByLabelText("Contract end")).toHaveValue("2026-11-18");
  });

  it("GM previews automatically once the draft is computable — no manual Preview click", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(new Error("none"));
    const preview = vi.spyOn(api, "previewCommercial").mockResolvedValue({
      computed: {
        complete: true,
        gm_us: null,
        gm_india: "0.60",
        policy: { requires_ceo: false },
      } as never,
    });
    render(<CommercialModelEditor snap={snap()} />);
    // Any edit leaves a complete, computable draft; the preview follows
    // by itself (debounced), labeled provisional.
    fireEvent.change(screen.getByLabelText("Contract fee"), {
      target: { value: "75400" },
    });
    await waitFor(() => expect(preview).toHaveBeenCalled(), { timeout: 4000 });
    await screen.findByText("GM within policy");
    const note = screen.getByTestId("approval-flow-note");
    expect(note).toHaveTextContent("no CEO step");
    expect(note).toHaveTextContent("Save version to publish");
    // It is a preview: nothing was saved.
    expect(api.saveCommercialVersion).toBeDefined();
  });

  it("the approval-flow note names the CEO step while GM is below floor or unassessed", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(new Error("none"));
    vi.spyOn(api, "previewCommercial").mockResolvedValue({
      computed: {
        complete: true,
        gm_us: null,
        gm_india: "0.20",
        policy: { requires_ceo: true },
      } as never,
    });
    render(<CommercialModelEditor snap={snap()} />);
    fireEvent.change(screen.getByLabelText("Contract fee"), {
      target: { value: "10000" },
    });
    await screen.findByText("CEO exception required", undefined, { timeout: 4000 });
    expect(screen.getByTestId("approval-flow-note")).toHaveTextContent(
      "CEO exception step, which is added automatically",
    );
  });

  it("an unsaved draft survives unmount and remount (tab navigation)", async () => {
    vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(new Error("none"));
    const snapshot = snap();
    const view = render(<CommercialModelEditor snap={snapshot} />);
    fireEvent.change(screen.getByLabelText("Contract fee"), {
      target: { value: "99999" },
    });
    view.unmount();
    render(<CommercialModelEditor snap={snap()} />);
    expect(screen.getByLabelText("Contract fee")).toHaveValue("99999");
    expect(screen.getByTestId("draft-state")).toHaveTextContent("Unsaved draft");
  });
});
