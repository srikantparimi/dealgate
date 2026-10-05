import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import * as api from "../../api/commercial";
import * as client from "../../api/client";
import {
  CommercialModelEditor,
  resetCommercialDraftCache,
} from "../../pages/v2/sow-workspace/CommercialModelEditor";
import { StaffingGmTab } from "../../pages/v2/sow-workspace/StaffingGmTab";
import type { WorkspaceSnapshot } from "../../pages/v2/sow-workspace/readiness";

const inputs: api.CommercialComponent = {
  component_id: "assessment",
  version: "1",
  source_id: "sow",
  source_version: "version",
  workstream_id: "assessment",
  profile: "fixed_assignment",
  profile_version: "1",
  policy_version: "policy",
  source_evidence: ["SOW page 2"],
  service_start: "2026-10-01",
  service_end: "2026-10-31",
  timezone: "America/New_York",
  currency: "USD",
  billing_cadence: "on_completion",
  cost_basis: "loaded",
  costs_confirmed: true,
  costs: [
    {
      source_id: "cost-one",
      month: "2026-10-01",
      location: "US",
      amount: "10000",
    },
  ],
  pricing: {
    total_fee: "24000",
    allocations: [{ month: "2026-10-01", location: "US", weight: "1" }],
    allocation_basis: "Confirmed October service",
    minor_unit: "0.01",
  },
  staffing: [],
};
function snapshot(component = inputs): WorkspaceSnapshot {
  return {
    deal: { id: "deal" },
    sow: { id: "version", sow_id: "sow", extracted_fields: {} },
    gmModel: {
      id: "gm-one",
      commercial_inputs: component,
      commercial_snapshot: {
        schedule: {
          rows: [
            {
              month: "2026-10-01",
              location: "US",
              revenue: "24000",
              cost: "10000",
            },
          ],
          children: [],
          missing: [],
          status: "ok",
        },
      },
    },
  } as unknown as WorkspaceSnapshot;
}
beforeEach(() => {
  vi.restoreAllMocks();
  resetCommercialDraftCache();
  vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(
    new Error("no advice in this test"),
  );
  vi.spyOn(api, "getCommercialProposal").mockRejectedValue(new Error("403"));
  vi.spyOn(client, "getMe").mockResolvedValue({
    groups: ["Delivery"],
  } as client.MeResponse);
  vi.spyOn(api, "getCommercialProfiles").mockResolvedValue({
    profiles: [],
    calculation_version: "v1",
    policy: { version: "policy", us_floor: "0.35", india_floor: "0.50" },
  });
});
describe("Commercial model editor", () => {
  it("keeps the signed SOW financial basis read-only for a writing role", async () => {
    const snap = snapshot();
    snap.approvalPackage = {
      sow_version_id: "version",
      status: "released",
    } as WorkspaceSnapshot["approvalPackage"];
    await act(async () => {
      render(<CommercialModelEditor snap={snap} />);
    });
    expect(
      screen.getByText(
        "Signed financial basis. Changes require a separate amendment version.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Contract fee")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();
  });
  it("prefills confirmed SOW evidence, leaving disputed currency and unknown costing unresolved", async () => {
    const snap = snapshot();
    snap.gmModel = null;
    snap.sow!.extracted_fields = {
      price: { value: "420000.00", status: "confirmed", page_ref: 2 },
      term_start: { value: "2026-11-01", status: "confirmed", page_ref: 2 },
      currency: { value: "USD", status: "disputed", page_ref: 2 },
    };
    await act(async () => {
      render(<CommercialModelEditor snap={snap} />);
    });
    expect(screen.getByLabelText("Contract fee")).toHaveValue("420000.00");
    expect(screen.getByLabelText("Contract start")).toHaveValue("2026-11-01");
    expect(screen.getByLabelText("Contract currency")).toHaveValue("");
    expect(screen.getByLabelText("Source evidence")).toHaveValue(
      "SOW version, price, page 2\nSOW version, term_start, page 2",
    );
    expect(screen.getByLabelText("Cost basis")).toHaveValue("");
    expect(
      screen.getByLabelText("All delivery costs confirmed"),
    ).not.toBeChecked();
  });
  it("never renders empty legacy resources for a redacted commercial model", async () => {
    const snap = snapshot();
    snap.gmModel!.commercial_profile = "hybrid";
    delete snap.gmModel!.commercial_inputs;
    delete snap.gmModel!.commercial_snapshot;
    await act(async () => {
      render(<StaffingGmTab snap={snap} />);
    });
    expect(
      screen.getByText("Commercial cost details are restricted."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Auto-staffing produced no resource lines"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Save version" }),
    ).not.toBeInTheDocument();
  });
  it("prefills exact decimal inputs and saves a new optimistic version without losing evidence", async () => {
    const save = vi.spyOn(api, "saveCommercialVersion").mockResolvedValue({
      gm_model: { ...snapshot().gmModel!, id: "gm-two" },
    });
    render(<CommercialModelEditor snap={snapshot()} />);
    expect(screen.getByLabelText("Contract fee")).toHaveValue("24000");
    fireEvent.change(screen.getByLabelText("Change reason"), {
      target: { value: "Confirmed loaded cost" },
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Save version" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save version" }));
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith(
        "deal",
        expect.objectContaining({
          expected_gm_model_id: "gm-one",
          sow_version_id: "version",
          inputs: expect.objectContaining({
            source_evidence: ["SOW page 2"],
            costs: inputs.costs,
            pricing: inputs.pricing,
          }),
        }),
      ),
    );
    await screen.findByText("Commercial version saved.");
  });
  it("displays server monthly values and a stale-save error without discarding edits", async () => {
    vi.spyOn(api, "saveCommercialVersion").mockRejectedValue(
      new Error("409: Commercial version changed. Refresh and review."),
    );
    render(<CommercialModelEditor snap={snapshot()} />);
    expect(screen.getByText("24000")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Contract fee"), {
      target: { value: "25000.01" },
    });
    fireEvent.change(screen.getByLabelText("Change reason"), {
      target: { value: "Revised scope" },
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Save version" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save version" }));
    expect(await screen.findByTestId("commercial-error")).toHaveTextContent("409");
    expect(screen.getByLabelText("Contract fee")).toHaveValue("25000.01");
  });
  it("never enables writes for Finance and preserves hybrid inputs read-only", async () => {
    vi.spyOn(client, "getMe").mockResolvedValue({
      groups: ["Finance"],
    } as client.MeResponse);
    await act(async () => {
      render(
        <CommercialModelEditor
          snap={snapshot({
            ...inputs,
            profile: "hybrid",
            pricing: { components: [inputs] },
          })}
        />,
      );
    });
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();
    expect(screen.getByLabelText("Contract fee")).toBeDisabled();
    expect(screen.getByText("hybrid")).toBeInTheDocument();
    expect(screen.getByText("24000")).toBeInTheDocument();
  });
  it("disables supported profile editing for a non-writing role", async () => {
    vi.spyOn(client, "getMe").mockResolvedValue({
      groups: ["Finance"],
    } as client.MeResponse);
    await act(async () => {
      render(<CommercialModelEditor snap={snapshot()} />);
    });
    expect(screen.getByLabelText("Contract fee")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();
  });
  it("previews recurring MSP without losing contractual adjustments or usage", async () => {
    const pricing = {
      fees: [{ location: "India", amount: "30000.10" }],
      proration: "calendar_days",
      included_scope: "24x7 monitoring",
      adjustments: [
        {
          source_id: "credit",
          month: "2026-10-01",
          location: "India",
          kind: "credit",
          amount: "10.00",
        },
      ],
      usage: [
        {
          source_id: "usage",
          month: "2026-10-01",
          location: "India",
          unit: "ticket",
          quantity: "3",
          included_quantity: "2",
          unit_rate: "1.10",
        },
      ],
    };
    const preview = vi.spyOn(api, "previewCommercial").mockResolvedValue({});
    render(
      <CommercialModelEditor
        snap={snapshot({ ...inputs, profile: "recurring_msp", pricing })}
      />,
    );
    expect(screen.getByLabelText("Monthly fee 1")).toHaveValue("30000.10");
    fireEvent.change(screen.getByLabelText("Monthly fee 1"), {
      target: { value: "31000.10" },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Preview" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    await waitFor(() =>
      expect(preview).toHaveBeenCalledWith(
        expect.objectContaining({
          pricing: {
            ...pricing,
            fees: [{ location: "India", amount: "31000.10" }],
          },
        }),
      ),
    );
  });
  it("retains missing cost and unconfirmed values rather than filling invented hours", async () => {
    const preview = vi.spyOn(api, "previewCommercial").mockResolvedValue({
      commercial_snapshot: {
        schedule: {
          rows: [],
          status: "incomplete",
          missing: [{ field: "cost_basis", reason: "Cost basis unconfirmed" }],
        },
      },
    });
    render(
      <CommercialModelEditor
        snap={snapshot({
          ...inputs,
          costs: [],
          costs_confirmed: false,
          cost_basis: null,
          currency: null,
        })}
      />,
    );
    expect(screen.getByLabelText("Contract currency")).toHaveValue("");
    expect(screen.getByLabelText("Cost basis")).toHaveValue("");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Preview" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    await screen.findByText("Cost basis unconfirmed");
    expect(preview).toHaveBeenCalledWith(
      expect.objectContaining({
        costs: [],
        costs_confirmed: false,
        staffing: [],
      }),
    );
  });
});
