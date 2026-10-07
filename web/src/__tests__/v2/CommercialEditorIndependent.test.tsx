import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/commercial";
import * as client from "../../api/client";
import { CommercialModelEditor } from "../../pages/v2/sow-workspace/CommercialModelEditor";
import { StaffingGmTab } from "../../pages/v2/sow-workspace/StaffingGmTab";
import { resetCommercialDraftCache } from "../../pages/v2/sow-workspace/CommercialModelEditor";
import type { WorkspaceSnapshot } from "../../pages/v2/sow-workspace/readiness";

const profiles = ["fixed_assignment", "recurring_msp", "calendar_staff_aug", "tm", "milestone", "unit", "hybrid"];
const sourceEvidence = ["SOW page 7, clause 4.2", "Manual confirmation: signed pricing appendix"];
const quantity = { source_id: "quantity-source", month: "2026-10-01", location: "US", quantity: "13.750001" };

function assignment(): api.CommercialStaffing {
  return {
    assignment_id: "assignment-one", source_id: "sow-a", source_version: "version-a",
    component_id: "component-calendar_staff_aug", profile_version: "1", policy_version: "policy-old",
    role: "Engineer", location: "US", timezone: "America/New_York", currency: "USD",
    quantity: 2, allocation: "0.375", bill_rate: "125.000001", cost_rate: null,
    rate_version: "rates-2026", cost_version: null, start: "2026-10-01", end: "2026-10-31",
    calendar: {
      calendar_id: "client-calendar", version: "revision-4", timezone: "America/New_York",
      coverage_start: "2026-10-01", coverage_end: "2026-10-31",
      week: Array.from({ length: 7 }, (_, i) => ({ scheduled: i < 5 ? "8" : "0", billable: i < 5 ? "7.5" : "0", paid: i < 5 ? "8" : "0" })),
      overrides: [{ day: "2026-10-12", hours: { scheduled: "0", billable: "0", paid: "8" }, reason: "Paid holiday; no client billing" }],
    },
  };
}

function component(profile: string): api.CommercialComponent {
  const pricing: Record<string, api.CommercialPricing> = {
    fixed_assignment: { total_fee: "12345.678901", allocations: [{ month: "2026-10-01", location: "US", weight: "1" }], allocation_basis: "Confirmed service", minor_unit: "0.000001" },
    recurring_msp: {
      fees: [{ location: "US", amount: "12345.678901" }], proration: "calendar_days", included_scope: "13 tickets",
      adjustments: [{ source_id: "credit-source", month: "2026-10-01", location: "US", kind: "credit", amount: "41.125001" }],
      usage: [{ ...quantity, unit: "ticket", included_quantity: "2.5", unit_rate: "9.250001" }],
    },
    calendar_staff_aug: { rates: [{ assignment_id: "assignment-one", basis: "daily", rate: "999.000001", version: "rates-2026", hours_per_day: "7.5", proration: null }] },
    tm: { rate: "125.000001", unit: "hour", estimates: [quantity], approved_usage: [{ ...quantity, source_id: "approved-source", quantity: "12.5" }], cap: "20000", minimum: null, calendar_estimates: false },
    milestone: { milestones: [{ milestone_id: "milestone-one", planned_date: "2026-10-19", location: "US", amount: "12345.678901", acceptance_conditions: "Client signoff", approved_invoice_ref: "invoice-42", recognized_revenue_ref: "ledger-42" }] },
    unit: { rate: "125.000001", unit: "story point", quantities: [quantity], contractual_basis: "billable_units" },
  };
  return {
    component_id: `component-${profile}`, version: "3", source_id: "sow-a", source_version: "version-a",
    workstream_id: "Service A", profile, profile_version: "1", policy_version: "policy-old",
    source_evidence: [...sourceEvidence], service_start: "2026-10-01", service_end: "2026-10-31",
    timezone: "America/New_York", currency: "USD", billing_cadence: "monthly", cost_basis: "loaded",
    costs_confirmed: false, costs: [{ source_id: "cost-source", month: "2026-10-01", location: "US", amount: null }],
    staffing: profile === "calendar_staff_aug" ? [assignment()] : [],
    pricing: profile === "hybrid" ? {
      components: [component("unit")], shared_cost_allocations: [{ source_id: "cost-source", component_id: "component-unit", weight: "1" }],
      allocation_basis: "Direct service attribution", minor_unit: "0.01",
      fx_rates: [{ currency: "INR", rate: "0.012345678901", version: "fx-2026-10", as_of: "2026-10-01" }],
    } : pricing[profile] ?? null,
  };
}

function snapshot(inputs: api.CommercialComponent): WorkspaceSnapshot {
  return {
    deal: { id: "deal-a" }, sow: { id: "version-a", sow_id: "sow-a" },
    gmModel: { id: "gm-a", commercial_profile: inputs.profile, commercial_inputs: inputs },
    approvalPackage: null, signedSow: null,
  } as unknown as WorkspaceSnapshot;
}

async function preview() {
  await waitFor(() => expect(api.previewCommercial).toHaveBeenCalled(), { timeout: 3000 });
}

beforeEach(() => {
  vi.restoreAllMocks();
  resetCommercialDraftCache();
  vi.spyOn(api, "getCommercialDraft").mockResolvedValue({ exists: false });
  vi.spyOn(api, "putCommercialDraft").mockResolvedValue({ exists: true, updated_at: "2026-10-06T00:00:00+00:00" });
  vi.spyOn(api, "deleteCommercialDraft").mockResolvedValue(undefined);
  vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(new Error("no advice"));
  vi.spyOn(api, "getCommercialProposal").mockRejectedValue(new Error("403"));
  vi.spyOn(client, "getMe").mockResolvedValue({ groups: ["Delivery"] } as client.MeResponse);
  vi.spyOn(api, "getCommercialProfiles").mockResolvedValue({
    profiles: profiles.map((key) => ({ key, version: "1", required_fields: [], calculation_available: true })),
    calculation_version: "engine-v1", policy: { version: "policy-active", us_floor: "0.35", india_floor: "0.50" },
  });
  vi.spyOn(api, "previewCommercial").mockResolvedValue({});
  vi.spyOn(api, "saveCommercialVersion").mockRejectedValue(new Error("Unexpected save in preview-only test"));
});

describe("Independent commercial editor boundary checks", () => {
  it("replaces a legacy calendar only when the user enters explicit total hours", async () => {
    const inputs = component("calendar_staff_aug");
    render(<CommercialModelEditor snap={snapshot(inputs)} />);
    expect(await screen.findByLabelText("Hours 1")).toHaveValue("");
    expect(screen.queryByRole("region", { name: "Calendar calculation details" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Hours 1"), { target: { value: "120" } });
    await preview();
    expect(vi.mocked(api.previewCommercial).mock.calls.at(-1)![0].staffing[0]).toMatchObject({
      hours_billable: "120",
      calendar: null,
    });
  });

  it.each(profiles)("preserves exact canonical %s inputs during a contract edit", async (profile) => {
    const inputs = component(profile);
    const original = structuredClone(inputs);
    render(<CommercialModelEditor snap={snapshot(inputs)} />);
    fireEvent.change(screen.getByLabelText("Contract currency", { exact: true }), { target: { value: "EUR" } });
    await preview();
    const expected = structuredClone(original);
    expected.currency = "EUR";
    expected.policy_version = "policy-active";
    expected.cost_basis = null;
    expected.costs_confirmed = true;
    for (const row of expected.staffing) row.policy_version = "policy-active";
    for (const child of expected.pricing?.components ?? []) child.policy_version = "policy-active";
    expect(api.previewCommercial).toHaveBeenLastCalledWith(expected);
    expect(inputs).toEqual(original);
  });

  it("does not apply a removed hybrid child's pending model change to its sibling", async () => {
    const inputs = component("hybrid");
    inputs.pricing!.components = [component("fixed_assignment"), component("unit")];
    render(<CommercialModelEditor snap={snapshot(inputs)} />);
    await waitFor(() => expect(screen.getByLabelText("Pricing profile", { exact: true })).toBeEnabled());
    fireEvent.change(within(screen.getByRole("region", { name: "Component 1" })).getByLabelText("Component pricing profile"), { target: { value: "milestone" } });
    fireEvent.click(screen.getByRole("button", { name: "Remove component 1" }));
    expect(screen.queryByRole("button", { name: "Replace component pricing" })).not.toBeInTheDocument();
    await preview();
    expect(vi.mocked(api.previewCommercial).mock.calls.at(-1)![0].pricing!.components![0].pricing).toEqual(component("unit").pricing);
  });

  it("never relabels unsaved preview values as a saved calculation after another edit", async () => {
    const snap = snapshot(component("fixed_assignment"));
    snap.gmModel!.commercial_snapshot = { schedule: { status: "ok", missing: [], rows: [{ month: "2026-10-01", location: "US", revenue: "111.11", cost: "22.22" }] } };
    vi.mocked(api.previewCommercial).mockResolvedValue({ commercial_snapshot: { schedule: { status: "ok", missing: [], rows: [{ month: "2026-10-01", location: "US", revenue: "999.99", cost: "88.88" }] } } });
    render(<CommercialModelEditor snap={snap} />);
    await preview();
    expect(await screen.findByText("Unsaved preview")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Contract fee", { exact: true }), { target: { value: "12346" } });
    expect(screen.queryByText("Saved calculation; edits not calculated")).not.toBeInTheDocument();
    expect(api.saveCommercialVersion).not.toHaveBeenCalled();
  });

  it.each(["fixed_assignment", "recurring_msp"])("allows adding the first cost-calendar assignment for %s", async (profile) => {
    render(<CommercialModelEditor snap={snapshot(component(profile))} />);
    await waitFor(() => expect(screen.getByLabelText("Pricing profile", { exact: true })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Add role" }));
    expect(screen.getByLabelText("Cost per hour 1")).toHaveValue("");
    expect(screen.getByLabelText("People 1")).toHaveValue(1);
  });

  it.each(["credit", "usage"])("exposes an existing MSP %s value for correction", async (kind) => {
    render(<CommercialModelEditor snap={snapshot(component("recurring_msp"))} />);
    await waitFor(() => expect(screen.getByLabelText("Pricing profile", { exact: true })).toBeEnabled());
    const original = kind === "credit" ? "41.125001" : "9.250001";
    const input = screen.getByDisplayValue(original);
    expect(input).toBeEnabled();
    fireEvent.change(input, { target: { value: "17.000001" } });
    await preview();
    const pricing = vi.mocked(api.previewCommercial).mock.calls.at(-1)![0].pricing!;
    if (kind === "credit") expect(pricing.adjustments).toEqual([{ source_id: "credit-source", month: "2026-10-01", location: "US", kind: "credit", amount: "17.000001" }]);
    else expect(pricing.usage).toEqual([{ ...quantity, unit: "ticket", included_quantity: "2.5", unit_rate: "17.000001" }]);
  });

  it("explains an unsupported persisted model instead of silently hiding its editor", async () => {
    await act(async () => { render(<CommercialModelEditor snap={snapshot(component("custom_formula"))} />); });
    expect(screen.getByRole("alert")).toHaveTextContent(/unsupported|unrecognized/i);
    expect(api.previewCommercial).not.toHaveBeenCalled();
    expect(api.saveCommercialVersion).not.toHaveBeenCalled();
  });

  it.each(["calendar_staff_aug", "hybrid"])("keeps Finance's %s controls read-only", async (profile) => {
    vi.mocked(client.getMe).mockResolvedValue({ groups: ["Finance"] } as client.MeResponse);
    await act(async () => { render(<CommercialModelEditor snap={snapshot(component(profile))} />); });
    expect(screen.getByLabelText("Pricing profile", { exact: true })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByRole("button", { name: profile === "hybrid" ? "Add component" : "Add role" })).toBeDisabled();
  });

  it.each(["calendar_staff_aug", "hybrid"])("locks verified but not yet released %s contracts", async (profile) => {
    const snap = snapshot(component(profile));
    snap.approvalPackage = { sow_version_id: "version-a", status: "ready_to_sign" } as WorkspaceSnapshot["approvalPackage"];
    snap.signedSow = { verify_status: "verified" } as WorkspaceSnapshot["signedSow"];
    await act(async () => { render(<CommercialModelEditor snap={snap} />); });
    expect(screen.getByLabelText("Pricing profile", { exact: true })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("resets the commercial source through the actual tab when the selected SOW changes", async () => {
    const first = snapshot(component("unit"));
    const view = render(<StaffingGmTab snap={first} />);
    fireEvent.change(await screen.findByLabelText("Contract currency", { exact: true }), { target: { value: "EUR" } });
    const next = snapshot(component("unit"));
    next.sow!.id = "version-b";
    next.sow!.sow_id = "sow-b";
    next.gmModel!.id = "gm-b";
    next.gmModel!.commercial_inputs!.source_id = "sow-b";
    next.gmModel!.commercial_inputs!.source_version = "version-b";
    next.gmModel!.commercial_inputs!.source_evidence = ["New SOW page 9"];
    view.rerender(<StaffingGmTab snap={next} />);
    expect(screen.getByLabelText("Contract currency", { exact: true })).toHaveValue("USD");
    vi.mocked(api.previewCommercial).mockClear();
    fireEvent.change(screen.getByLabelText("Contract currency", { exact: true }), { target: { value: "GBP" } });
    await preview();
    expect(api.previewCommercial).toHaveBeenLastCalledWith(expect.objectContaining({ source_id: "sow-b", source_version: "version-b", source_evidence: ["New SOW page 9"] }));
  });
});
