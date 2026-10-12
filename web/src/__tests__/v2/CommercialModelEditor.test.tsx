import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as api from "../../api/commercial";
import * as client from "../../api/client";
import {
  CommercialModelEditor,
  resetCommercialDraftCache,
} from "../../pages/v2/sow-workspace/CommercialModelEditor";
import { StaffingGmTab } from "../../pages/v2/sow-workspace/StaffingGmTab";
import type { WorkspaceSnapshot } from "../../pages/v2/sow-workspace/readiness";

const staffing: api.CommercialStaffing = {
  assignment_id: "resource-one",
  source_id: "sow",
  source_version: "version",
  component_id: "assessment",
  profile_version: "1",
  policy_version: "policy",
  role: "Intune Consultant",
  seniority: "Senior",
  location: "US",
  timezone: "America/New_York",
  currency: "USD",
  quantity: 1,
  allocation: "0.5",
  hours_billable: "960",
  calendar: null,
  bill_rate: null,
  cost_rate: "70",
  rate_version: null,
  cost_version: "rate-card",
  cost_rate_basis: "hourly",
  start: "2026-10-01",
  end: "2026-12-01",
};

const inputs: api.CommercialComponent = {
  component_id: "assessment",
  version: "1",
  source_id: "sow",
  source_version: "version",
  workstream_id: "delivery",
  profile: "fixed_assignment",
  profile_version: "1",
  policy_version: "policy",
  source_evidence: ["SOW page 2"],
  service_start: "2026-10-01",
  service_end: "2026-12-01",
  timezone: "America/New_York",
  currency: "USD",
  billing_cadence: "monthly",
  cost_basis: null,
  costs_confirmed: false,
  costs: [{
    source_id: "cost-one",
    description: "Travel",
    month: "2026-10-01",
    location: "US",
    amount: "1000",
  }],
  pricing: {
    total_fee: "75400",
    allocations: [
      { month: "2026-10-01", location: "US", weight: "1" },
      { month: "2026-11-01", location: "US", weight: "1" },
      { month: "2026-12-01", location: "US", weight: "1" },
    ],
    allocation_basis: "even service months",
    minor_unit: "0.01",
  },
  staffing: [staffing],
};

function snapshot(component = inputs): WorkspaceSnapshot {
  return {
    deal: { id: "deal" },
    sow: { id: "version", sow_id: "sow", extracted_fields: {} },
    gmModel: {
      id: "gm-one",
      commercial_inputs: component,
      commercial_snapshot: {
        schedule: { rows: [], children: [], missing: [], status: "ok" },
      },
    },
  } as unknown as WorkspaceSnapshot;
}

beforeEach(() => {
  vi.restoreAllMocks();
  resetCommercialDraftCache();
  vi.spyOn(api, "getCommercialDraft").mockResolvedValue({ exists: false });
  vi.spyOn(api, "putCommercialDraft").mockResolvedValue({
    exists: true,
    updated_at: "2026-10-06T00:00:00+00:00",
  });
  vi.spyOn(api, "deleteCommercialDraft").mockResolvedValue(undefined);
  vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(new Error("not needed"));
  vi.spyOn(api, "getCommercialProposal").mockRejectedValue(new Error("not needed"));
  vi.spyOn(api, "previewCommercial").mockResolvedValue({});
  vi.spyOn(client, "getMe").mockResolvedValue({ groups: ["Delivery"] } as client.MeResponse);
  vi.spyOn(api, "getCommercialProfiles").mockResolvedValue({
    profiles: [],
    calculation_version: "v1",
    policy: { version: "policy", us_floor: "0.35", india_floor: "0.50" },
  });
});

describe("simplified Staffing & GM editor", () => {
  it("shows the compact contract, staffing and additional-cost surface", async () => {
    await act(async () => render(<CommercialModelEditor snap={snapshot()} />));

    expect(screen.getByLabelText("Contract fee")).toHaveValue("75400");
    expect(screen.getByLabelText("Billing schedule")).toHaveValue("monthly");
    expect(screen.getByRole("option", { name: "Weekly" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Bi-weekly" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Fixed after project delivery" })).toBeInTheDocument();
    expect(screen.getByLabelText("Role 1")).toHaveValue("Intune Consultant");
    expect(screen.getByLabelText("Seniority 1")).toHaveValue("Senior");
    expect(screen.getByLabelText("Hours 1")).toHaveValue("960");
    expect(screen.getByLabelText("Utilization 1")).toHaveValue("50");
    expect(screen.getByLabelText("Additional cost description 1")).toHaveValue("Travel");

    expect(screen.queryByLabelText("Cost basis")).not.toBeInTheDocument();
    expect(screen.queryByText(/Monthly plan & expenses/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Review & save/)).not.toBeInTheDocument();
    expect(screen.queryByText(/working calendar/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("drops an empty legacy calendar before previewing the simple hours model", async () => {
    const preview = vi.spyOn(api, "previewCommercial");
    const blankWeek = Array.from({ length: 7 }, () => ({
      scheduled: "",
      billable: "",
      paid: "",
    }));
    const legacyStaffing: api.CommercialStaffing = {
      ...staffing,
      hours_billable: null,
      calendar: {
        calendar_id: "legacy-empty",
        version: "draft",
        timezone: "America/New_York",
        coverage_start: "2026-10-01",
        coverage_end: "2026-12-01",
        week: blankWeek,
        overrides: [],
      },
    };

    render(
      <CommercialModelEditor
        snap={snapshot({ ...inputs, staffing: [legacyStaffing] })}
      />,
    );

    expect(await screen.findByLabelText("Hours 1")).toHaveValue("");
    await waitFor(() => expect(preview).toHaveBeenCalled(), { timeout: 2500 });
    expect(preview.mock.calls.at(-1)?.[0].staffing[0].calendar).toBeNull();
  });

  it("saves total hours and additional costs as the authoritative version", async () => {
    const save = vi.spyOn(api, "saveCommercialVersion").mockResolvedValue({
      gm_model: { ...snapshot().gmModel!, id: "gm-two" },
    });
    render(<CommercialModelEditor snap={snapshot()} />);

    fireEvent.change(await screen.findByLabelText("Hours 1"), { target: { value: "800" } });
    fireEvent.change(screen.getByLabelText("Additional cost amount 1"), { target: { value: "2500" } });
    fireEvent.change(screen.getByLabelText("Billing schedule"), { target: { value: "biweekly" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    const body = save.mock.calls[0][1];
    expect(body.change_reason).toBe("Staffing and GM checkpoint saved");
    expect(body.inputs.billing_cadence).toBe("biweekly");
    expect(body.inputs.cost_basis).toBeNull();
    expect(body.inputs.costs_confirmed).toBe(true);
    expect(body.inputs.staffing[0].hours_billable).toBe("800");
    expect(body.inputs.staffing[0].calendar).toBeNull();
    expect(body.inputs.costs[0]).toEqual(expect.objectContaining({
      description: "Travel",
      amount: "2500",
    }));
  });

  it("adds and removes simple resource and cost rows", async () => {
    render(<CommercialModelEditor snap={snapshot({ ...inputs, staffing: [], costs: [] })} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add role" }));
    expect(screen.getByLabelText("Role 1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add cost" }));
    expect(screen.getByLabelText("Additional cost amount 1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove role 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove additional cost 1" }));
    expect(screen.queryByLabelText("Role 1")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Additional cost amount 1")).not.toBeInTheDocument();
  });

  it("keeps signed financial basis read-only", async () => {
    const snap = snapshot();
    snap.approvalPackage = { sow_version_id: "version", status: "released" } as WorkspaceSnapshot["approvalPackage"];
    await act(async () => render(<CommercialModelEditor snap={snap} />));
    expect(screen.getByText(/Signed financial basis/)).toBeInTheDocument();
    expect(screen.getByLabelText("Contract fee")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("retains edits when a stale save is rejected", async () => {
    vi.spyOn(api, "saveCommercialVersion").mockRejectedValue(new Error("409: version changed"));
    render(<CommercialModelEditor snap={snapshot()} />);
    fireEvent.change(await screen.findByLabelText("Contract fee"), { target: { value: "76000" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByTestId("commercial-error")).toHaveTextContent("409");
    expect(screen.getByLabelText("Contract fee")).toHaveValue("76000");
  });

  it("keeps redacted commercial models off the legacy empty-resource path", async () => {
    const snap = snapshot();
    snap.gmModel!.commercial_profile = "hybrid";
    delete snap.gmModel!.commercial_inputs;
    delete snap.gmModel!.commercial_snapshot;
    await act(async () => render(<StaffingGmTab snap={snap} />));
    expect(screen.getByText("Commercial cost details are restricted.")).toBeInTheDocument();
    expect(screen.queryByText("Auto-staffing produced no resource lines")).not.toBeInTheDocument();
  });
});
