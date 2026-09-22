import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/client";
import { StaffingGmSection } from "../../pages/v2/sow-studio/confirmation/StaffingGmSection";

const resources = [{ role: "Engineer", seniority: "Senior", location: "US", person_name: null, utilization_pct: "100.0000", hours_billable: "240.0000", hourly_bill_rate: "0.0000", hourly_cost: "120.12345678", start_date: "2026-09-01", end_date: "2026-09-30" }];
const summary = { revenue: "50000", labor_cost: "28800", direct_cost: "1000", total_delivery_cost: "29800", gross_profit: "20200", labor_pct: "0.576", direct_pct: "0.02", total_cost_pct: "0.596", pass_through: "2300" };
const policy = { us_floor: "0.35", india_floor: "0.50", us_pass: true, india_pass: true, us_applicable: true, india_applicable: false, us_delta: "0.054", requires_ceo: false, failing: [] };
const computed = { gm_us: "0.404", gm_india: null, gm_blended: "0.404", finance_summary: summary, policy, complete: true };
const payload = {
  engagement: { primary: { type: "fixed_price" } },
  staffing: { lines: [{ ...resources[0], allocation_pct: "1", provenance: "manual" }], warnings: [] },
  gm_model: { id: "gm-before", cost_lines: [], version: 3 },
  floors: { ...policy, gm_us: "0.424", gm_india: null, gm_blended: "0.424", gm_version: 3 },
} as unknown as api.SowConfirmationPayload;
const canonicalResources: api.DeliveryResourceLineInput[] = [{ ...resources[0], location: "US", allocation_pct: "1", person_name: "Assigned engineer", validated_by: "hr-validator" }];
const state = { opportunity_id: "opp", gm_model_id: "gm-before", engagement_type: "fixed_price", resources, resource_lines: canonicalResources, cost_lines: [], total_price: "50000", is_signed: false, requires_notice_on_change: false, editable: true, margin: { gm_model_id: "gm-before", gm_version: 3 } } as api.SowResourcesState;

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "getDirectCostCategories").mockResolvedValue({ categories: ["Travel", "Software/licenses", "Other"] });
  vi.spyOn(api, "getSowStaffing").mockResolvedValue(state);
  vi.spyOn(api, "previewDeliveryModel").mockResolvedValue({ engagement_type: "fixed_price", computed, warnings: { capacity: [], hr: [] } } as unknown as api.DeliveryPreviewResponse);
  vi.spyOn(api, "putSowStaffing").mockResolvedValue({ gm_model_id: "gm-after" } as api.SowResourceUpdateResult);
});

describe("Direct costs on Confirm", () => {
  it("previews through the engine, saves both cost bases, and reloads immutable output", async () => {
    const saved = vi.fn();
    const dirty = vi.fn();
    const view = render(<StaffingGmSection payload={payload} opportunityId="opp" onSaved={saved} onDirtyChange={dirty} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add cost" }));
    expect(screen.getByRole("button", { name: "Save direct costs" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Cost category 1"), { target: { value: "Software/licenses" } });
    fireEvent.change(screen.getByLabelText("Cost basis 1"), { target: { value: "percent_revenue" } });
    fireEvent.change(screen.getByLabelText("Cost value 1"), { target: { value: "2" } });
    await waitFor(() => expect(api.previewDeliveryModel).toHaveBeenCalled());
    expect(screen.getByText("$29,800")).toBeInTheDocument();
    expect(screen.getAllByText("40.4%").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Add cost" }));
    fireEvent.change(screen.getByLabelText("Cost value 2"), { target: { value: "2300" } });
    fireEvent.click(screen.getByLabelText("Cost reimbursable 2"));
    await waitFor(() => expect(api.previewDeliveryModel).toHaveBeenLastCalledWith(expect.objectContaining({ inputs: expect.objectContaining({ cost_lines: [expect.objectContaining({ basis: "percent_revenue", basis_value: "2", location: "proportional" }), expect.objectContaining({ amount: "2300", reimbursable: true })] }) })));
    expect(screen.getByText("$2,300")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save direct costs" }));
    await waitFor(() => expect(saved).toHaveBeenCalledOnce());
    const body = vi.mocked(api.putSowStaffing).mock.calls[0][1];
    expect(body.cost_lines).toHaveLength(2);
    expect(body.resource_lines).toBeUndefined();
    expect(vi.mocked(api.previewDeliveryModel).mock.calls.at(-1)?.[0].inputs.resource_lines).toEqual(canonicalResources);
    expect(dirty).toHaveBeenLastCalledWith(false);
    vi.mocked(api.getSowStaffing).mockResolvedValue({ ...state, gm_model_id: "gm-after", cost_lines: body.cost_lines });
    view.rerender(<StaffingGmSection payload={{ ...payload, gm_model: { ...payload.gm_model!, id: "gm-after", version: 4, cost_lines: body.cost_lines }, floors: { ...payload.floors, ...computed, ...policy, gm_version: 4 } }} opportunityId="opp" onSaved={saved} onDirtyChange={dirty} />);
    expect(await screen.findByText("GM v4 · draft")).toBeInTheDocument();
    expect(screen.getByLabelText("Cost reimbursable 2")).toBeChecked();
  });

  it("keeps extracted unknown expenses blank until reviewed and never silently saves them", async () => {
    vi.mocked(api.getSowStaffing).mockResolvedValue({ ...state, direct_cost_proposals: [{ category: "Travel", note: "Expenses reimbursed by client", amount: null, basis_value: null, basis: "amount", location: "proportional", reimbursable: true, provenance: "extracted", source_ref: "SOW p. 4" }] });
    const dirty = vi.fn();
    render(<StaffingGmSection payload={payload} opportunityId="opp" onDirtyChange={dirty} />);
    expect(await screen.findByLabelText("Cost value 1")).toHaveValue(null);
    expect(screen.getByText("extracted")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save direct costs" })).toBeDisabled();
    expect(dirty).toHaveBeenLastCalledWith(true);
    expect(api.putSowStaffing).not.toHaveBeenCalled();
  });

  it("retains edits and exposes an engine failure", async () => {
    vi.mocked(api.previewDeliveryModel).mockRejectedValue(new Error("Finance engine unavailable"));
    render(<StaffingGmSection payload={payload} opportunityId="opp" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add cost" }));
    fireEvent.change(screen.getByLabelText("Cost value 1"), { target: { value: "1000" } });
    expect(screen.queryByText("42.4%")).not.toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Finance engine unavailable");
    expect(screen.getByLabelText("Cost value 1")).toHaveValue(1000);
  });

  it("retains a cost draft across unrelated confirmation updates and locks it while saving", async () => {
    let finishSave!: (value: api.SowResourceUpdateResult) => void;
    vi.mocked(api.putSowStaffing).mockImplementation(() => new Promise((resolve) => { finishSave = resolve; }));
    const dirty = vi.fn();
    const view = render(<StaffingGmSection payload={payload} opportunityId="opp" onDirtyChange={dirty} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add cost" }));
    fireEvent.change(screen.getByLabelText("Cost value 1"), { target: { value: "1000" } });
    view.rerender(<StaffingGmSection payload={{ ...payload, projected_tasks: [] }} opportunityId="opp" onDirtyChange={dirty} />);
    expect(screen.getByLabelText("Cost value 1")).toHaveValue(1000);
    expect(dirty).toHaveBeenLastCalledWith(true);
    fireEvent.click(screen.getByRole("button", { name: "Save direct costs" }));
    expect(screen.getByLabelText("Cost value 1")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add cost" })).toBeDisabled();
    finishSave({ gm_model_id: "new-gm" } as api.SowResourceUpdateResult);
    await waitFor(() => expect(dirty).toHaveBeenLastCalledWith(false));
  });

  it("does not offer direct-cost edits when costs are redacted", async () => {
    vi.mocked(api.getSowStaffing).mockResolvedValue({ ...state, cost_lines: undefined, resource_lines: undefined });
    render(<StaffingGmSection payload={payload} opportunityId="opp" />);
    await waitFor(() => expect(api.getSowStaffing).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Add cost" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save direct costs" })).not.toBeInTheDocument();
  });
});
