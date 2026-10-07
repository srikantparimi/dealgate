import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../../api/client";
import * as commercial from "../../api/commercial";
import { SowWorkspacePage } from "../../pages/v2/SowWorkspace";
import * as loader from "../../pages/v2/sow-workspace/dataLoader";
import type { WorkspaceSnapshot } from "../../pages/v2/sow-workspace/readiness";

const inputs: commercial.CommercialComponent = {
  component_id: "delivery",
  version: "1",
  source_id: "sow",
  source_version: "sow-version",
  workstream_id: "delivery",
  profile: "fixed_assignment",
  profile_version: "1",
  policy_version: "policy",
  source_evidence: ["SOW page 1"],
  service_start: "2026-10-01",
  service_end: "2026-12-01",
  timezone: "America/Los_Angeles",
  currency: "USD",
  billing_cadence: "on_completion",
  cost_basis: "loaded hourly cost",
  costs_confirmed: true,
  costs: [{ source_id: "team", month: "2026-10-01", location: "US", amount: "26400" }],
  staffing: [],
  pricing: {
    total_fee: "75400",
    allocations: [{ month: "2026-10-01", location: "US", weight: "1" }],
    allocation_basis: "confirmed service period",
    minor_unit: "0.01",
  },
};

const computed = {
  complete: true,
  gm_blended: "0.6498673740053050397877984085",
  gm_us: "0.6498673740053050397877984085",
  gm_india: null,
  policy: {
    requires_ceo: false,
    us_floor: "0.35",
    india_floor: "0.50",
    us_pass: true,
    india_pass: true,
    failing: [],
  },
  finance_summary: {
    revenue: "75400.00",
    labor_cost: "26400.00",
    direct_cost: "0.00",
    total_delivery_cost: "26400.00",
    gross_profit: "49000.00",
    labor_pct: "0.3501",
    direct_pct: "0.0000",
    total_cost_pct: "0.3501",
    pass_through: "0",
  },
};

function snapshot(saved: boolean): WorkspaceSnapshot {
  return {
    deal: {
      id: "deal",
      owner_id: "owner",
      client_name: "Connected test client",
      owner: { name: "Owner" },
      engagement_type: "fixed_price",
    },
    sow: {
      id: "sow-version",
      sow_id: "sow",
      version_no: 1,
      confirmed_at: "2026-10-06T00:00:00Z",
      extracted_fields: {},
    },
    gmModel: saved
      ? ({
          id: "gm-saved",
          version: 1,
          commercial_profile: "fixed_assignment",
          commercial_inputs: inputs,
          commercial_snapshot: {
            schedule: { rows: [], missing: [], status: "ok" },
          },
          computed,
          resource_lines: [],
          cost_lines: [],
          completeness_issues: [],
        } as never)
      : null,
    approvalPackage: null,
    agreements: [],
    signedSow: null,
  } as unknown as WorkspaceSnapshot;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(client, "getMe").mockResolvedValue({
    id: "owner",
    name: "Owner",
    email: "owner@example.test",
    groups: ["Delivery"],
  });
  vi.spyOn(client, "assessSowDeletion").mockRejectedValue(new Error("not needed"));
  vi.spyOn(commercial, "getCommercialDraft").mockResolvedValue({
    exists: true,
    inputs,
    sow_version_id: "sow-version",
    updated_at: "2026-10-06T00:00:00Z",
  });
  vi.spyOn(commercial, "putCommercialDraft").mockResolvedValue({
    exists: true,
    updated_at: "2026-10-06T00:01:00Z",
  });
  vi.spyOn(commercial, "deleteCommercialDraft").mockResolvedValue(undefined);
  vi.spyOn(commercial, "getCommercialProposal").mockRejectedValue(new Error("draft exists"));
  vi.spyOn(commercial, "getStaffingAdvice").mockRejectedValue(new Error("not needed"));
  vi.spyOn(commercial, "getCommercialProfiles").mockResolvedValue({
    profiles: [],
    calculation_version: "commercial-schedule-v1",
    policy: { version: "policy", us_floor: "0.35", india_floor: "0.50" },
  });
});

describe("workspace commercial primary action", () => {
  it("calculates, saves, reloads, then advances to approval instead of looping", async () => {
    vi.mocked(commercial.getCommercialDraft).mockResolvedValue({
      exists: true,
      inputs: { ...inputs, service_start: null, service_end: null },
      sow_version_id: "sow-version",
      updated_at: "2026-10-06T00:00:00Z",
    });
    vi.spyOn(loader, "loadWorkspace")
      .mockResolvedValueOnce({ snap: snapshot(false), degradedEndpoints: [] })
      .mockResolvedValue({ snap: snapshot(true), degradedEndpoints: [] });
    vi.spyOn(commercial, "previewCommercial").mockResolvedValue({
      computed: computed as never,
      commercial_snapshot: {
        schedule: { rows: [], missing: [], status: "ok" },
      },
    });
    const save = vi.spyOn(commercial, "saveCommercialVersion").mockResolvedValue({
      gm_model: snapshot(true).gmModel!,
    });

    render(
      <MemoryRouter initialEntries={["/sows/deal/staffing"]}>
        <Routes>
          <Route path="/sows/:id/:tab" element={<SowWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: "Staffing & GM" });
    fireEvent.change(screen.getByLabelText("Contract start"), {
      target: { value: "2026-10-01" },
    });
    fireEvent.change(screen.getByLabelText("Contract end"), {
      target: { value: "2026-12-01" },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Calculate financials" }));
    await waitFor(() => expect(commercial.previewCommercial).toHaveBeenCalled());
    fireEvent.click(
      within(screen.getByTestId("workspace-header")).getByRole("button", { name: "Save" }),
    );
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("button", { name: "Submit for approval" })).toBeVisible();
    expect(loader.loadWorkspace).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("tab", { name: "Staffing & GM" })).toHaveAttribute(
      "data-state",
      "active",
    );
  });

  it("keeps an invalid draft in place and focuses the named blocker", async () => {
    vi.mocked(commercial.getCommercialDraft).mockResolvedValue({
      exists: true,
      inputs: { ...inputs, billing_cadence: null },
      sow_version_id: "sow-version",
      updated_at: "2026-10-06T00:00:00Z",
    });
    const save = vi.spyOn(commercial, "saveCommercialVersion");
    vi.spyOn(loader, "loadWorkspace").mockResolvedValue({
      snap: snapshot(false),
      degradedEndpoints: [],
    });
    vi.spyOn(commercial, "previewCommercial").mockResolvedValue({
      computed: { ...computed, complete: false } as never,
      commercial_snapshot: {
        schedule: {
          rows: [],
          status: "incomplete",
          missing: [{ field: "billing_cadence", reason: "billing schedule is required" }],
        },
      },
    });

    render(
      <MemoryRouter initialEntries={["/sows/deal/staffing"]}>
        <Routes>
          <Route path="/sows/:id/:tab" element={<SowWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Calculate financials" }));
    const blocker = await screen.findByRole("button", { name: "Fix billing schedule" });
    fireEvent.click(blocker);
    await waitFor(() => expect(screen.getByLabelText("Billing schedule")).toHaveFocus());
    expect(save).not.toHaveBeenCalled();
    expect(screen.getByRole("tab", { name: "Staffing & GM" })).toHaveAttribute(
      "data-state",
      "active",
    );
  });
});
