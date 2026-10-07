/**
 * S22 · the commercial editor opens pre-filled from the SOW/auto-staffing
 * proposal when nothing is saved — human intervention only where needed,
 * every value editable, and a dirty form is never overwritten.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/commercial";
import * as client from "../../api/client";
import {
  CommercialModelEditor,
  resetCommercialDraftCache,
} from "../../pages/v2/sow-workspace/CommercialModelEditor";
import type { WorkspaceSnapshot } from "../../pages/v2/sow-workspace/readiness";

function emptySnapshot(): WorkspaceSnapshot {
  return {
    deal: { id: "deal-a" },
    sow: { id: "version-a", sow_id: "sow-a", extracted_fields: {} },
    gmModel: null,
    approvalPackage: null,
    signedSow: null,
  } as unknown as WorkspaceSnapshot;
}

function proposal(): api.CommercialProposal {
  return {
    component: {
      component_id: "proposed",
      version: "1",
      source_id: "sow-a",
      source_version: "version-a",
      workstream_id: "delivery",
      profile: "fixed_assignment",
      profile_version: "1",
      policy_version: "policy-active",
      source_evidence: ["sow-version:version-a"],
      service_start: "2026-10-01",
      service_end: "2027-03-31",
      timezone: "America/Los_Angeles",
      currency: "USD",
      billing_cadence: null,
      cost_basis: null,
      costs_confirmed: false,
      costs: [],
      staffing: [
        {
          assignment_id: "proposed-1",
          source_id: "sow-a",
          source_version: "version-a",
          component_id: "proposed",
          profile_version: "1",
          policy_version: "policy-active",
          role: "Engineer",
          seniority: "Senior",
          location: "US",
          timezone: "America/Los_Angeles",
          currency: "USD",
          quantity: 1,
          allocation: "0.5",
          hours_billable: "480",
          calendar: null,
          bill_rate: "150",
          cost_rate: "95",
          rate_version: "auto-staff",
          cost_version: "auto-staff",
          start: "2026-10-01",
          end: "2027-03-31",
          cost_rate_basis: "hourly",
          cost_proration: null,
        },
      ],
      pricing: {
        total_fee: "250000.00",
        allocations: [
          { month: "2026-10-01", location: "US", weight: "1" },
        ],
        allocation_basis: "even service months (proposed)",
        minor_unit: "0.01",
      },
    },
    provenance: { currency: "extracted", "pricing.amount": "extracted" },
    warnings: ["No auto-staffing lines were available for one role"],
    suggested_profile: "fixed_assignment",
    engagement_type: "fixed_price",
    saved_version_exists: false,
    sow_version_id: "version-a",
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  resetCommercialDraftCache();
  vi.spyOn(api, "getCommercialDraft").mockResolvedValue({ exists: false });
  vi.spyOn(api, "putCommercialDraft").mockResolvedValue({ exists: true, updated_at: "2026-10-06T00:00:00+00:00" });
  vi.spyOn(api, "deleteCommercialDraft").mockResolvedValue(undefined);
  vi.spyOn(api, "getStaffingAdvice").mockRejectedValue(
    new Error("no advice in this test"),
  );
  vi.spyOn(client, "getMe").mockResolvedValue({
    groups: ["Delivery"],
  } as client.MeResponse);
  vi.spyOn(api, "getCommercialProfiles").mockResolvedValue({
    profiles: [
      {
        key: "fixed_assignment",
        version: "1",
        required_fields: [],
        calculation_available: true,
      },
    ],
    calculation_version: "engine-v1",
    policy: { version: "policy-active", us_floor: "0.35", india_floor: "0.50" },
  });
  vi.spyOn(api, "previewCommercial").mockResolvedValue({});
  vi.spyOn(api, "saveCommercialVersion").mockRejectedValue(
    new Error("no save in this test"),
  );
});

describe("commercial proposal prefill", () => {
  it("prefills the empty editor from the proposal with a visible banner", async () => {
    vi.spyOn(api, "getCommercialProposal").mockResolvedValue(proposal());
    render(<CommercialModelEditor snap={emptySnapshot()} />);

    await screen.findByTestId("commercial-proposal-banner");
    expect(screen.getByTestId("proposal-warning")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByLabelText("Contract fee")).toHaveValue("250000.00"),
    );
    expect(screen.getByLabelText("Role 1")).toHaveValue("Engineer");
    expect(screen.getByLabelText("Seniority 1")).toHaveValue("Senior");
    // Stored fraction "0.5" displays as 50% — plain language, exact schema.
    expect(screen.getByLabelText("Utilization 1")).toHaveValue("50");
    expect(screen.getByLabelText("Hours 1")).toHaveValue("480");
  });

  it("offers reset after edits instead of silently overwriting", async () => {
    vi.spyOn(api, "getCommercialProposal").mockResolvedValue(proposal());
    render(<CommercialModelEditor snap={emptySnapshot()} />);
    const fee = await screen.findByLabelText("Contract fee");
    await waitFor(() => expect(fee).toHaveValue("250000.00"));

    fireEvent.change(fee, { target: { value: "99" } });
    expect(fee).toHaveValue("99");
    fireEvent.click(await screen.findByTestId("proposal-reset"));
    await waitFor(() => expect(fee).toHaveValue("250000.00"));
  });

  it("leaves the editor empty when no proposal is available", async () => {
    vi.spyOn(api, "getCommercialProposal").mockRejectedValue(
      new Error("403"),
    );
    render(<CommercialModelEditor snap={emptySnapshot()} />);
    await waitFor(() =>
      expect(api.getCommercialProposal).toHaveBeenCalledTimes(1),
    );
    expect(
      screen.queryByTestId("commercial-proposal-banner"),
    ).not.toBeInTheDocument();
  });
});
