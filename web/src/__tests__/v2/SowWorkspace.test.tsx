/**
 * S9 Wave 2 — Staffing & GM tab acceptance tests.
 *
 * The tab is exercised by rendering it directly with a mock
 * `WorkspaceSnapshot`, so the tests focus on:
 *   - provenance chip on every resource line
 *   - inline edit-in-place flips the row's provenance to `manual`
 *   - `FloorBar` renders per component (US / India / Blended)
 *   - a below-floor row surfaces "Fails by N pts" chip visually
 *   - `Rebuild from SOW` button appears when a newer sow_version exists
 *
 * The full workspace routing / dataLoader path is covered by existing
 * integration tests; this file exercises the new tab surface directly.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type {
  DeliveryGmModel,
  DeliveryResourceLineRow,
} from "../../api/client";
import { StaffingGmTab } from "../../pages/v2/sow-workspace/StaffingGmTab";
import type { WorkspaceSnapshot } from "../../pages/v2/sow-workspace/readiness";

function resourceLine(
  overrides: Partial<DeliveryResourceLineRow> = {},
): DeliveryResourceLineRow {
  return {
    id: overrides.id ?? "rl-1",
    role: "Engineer",
    seniority: "Senior",
    location: "US",
    person_name: "TBD",
    allocation_pct: "1.0",
    start_date: "2026-10-01",
    end_date: "2026-12-15",
    hours_billable: "400",
    hourly_bill_rate: "200",
    hourly_cost: "120",
    validated_by: null,
    provenance_meta: {
      provenance: "extracted",
      source_label: "extracted from SOW",
      page_ref: 4,
      confidence: 0.92,
    },
    ...overrides,
  };
}

function buildGm(
  overrides: Partial<DeliveryGmModel> = {},
): DeliveryGmModel {
  return {
    id: "gm-000000-aaaaaaaa",
    opportunity_id: "op-1",
    sow_version_id: "sv-1",
    engagement_type: "fixed_price",
    delivery_pattern: "milestone",
    contingency_pct: null,
    warranty_days: null,
    revenue_us: "90000",
    revenue_india: "55000",
    created_by: "u-1",
    created_at: "2026-09-19T00:00:00Z",
    resource_lines: [
      resourceLine({
        id: "rl-us",
        role: "Engineer",
        location: "US",
        hourly_bill_rate: "200",
        hourly_cost: "160",
        hours_billable: "450",
        provenance_meta: {
          provenance: "extracted",
          source_label: "extracted from SOW",
          page_ref: 4,
          confidence: 0.92,
        },
      }),
      resourceLine({
        id: "rl-in",
        role: "Analyst",
        seniority: "Mid",
        location: "India",
        hourly_bill_rate: "85",
        hourly_cost: "40",
        hours_billable: "400",
        provenance_meta: {
          provenance: "looked_up",
          source_label: "looked up · past SOW #A17",
          source_id: "past-sow-A17",
          warning: "estimated from past SOW",
        },
      }),
    ],
    cost_lines: [],
    completeness_issues: [],
    computed: {
      revenue_us: "90000",
      cost_us: "65000",
      gm_us: "0.278",
      revenue_india: "55000",
      cost_india: "30000",
      gm_india: "0.4545",
      gm_blended: "0.3448",
      geography: "Mixed",
      complete: true,
      missing: [],
      min_price_us: "100000",
      min_price_india: "60000",
      policy: {
        us_floor: "0.35",
        india_floor: "0.50",
        us_pass: false,
        india_pass: false,
        requires_ceo: true,
        failing: ["us", "india"],
      },
      computed_at: "2026-09-19T00:00:00Z",
    },
    latest_sow_version_id: "sv-1",
    ...overrides,
  };
}

function buildSnap(gm: DeliveryGmModel | null): WorkspaceSnapshot {
  return {
    deal: null,
    sow: null,
    gmModel: gm,
    approvalPackage: null,
    agreements: [],
    signedSow: null,
  };
}

function renderTab(
  gm: DeliveryGmModel | null,
  opts: {
    onSaveRow?: Parameters<typeof StaffingGmTab>[0]["onSaveRow"];
    onRebuildFromSow?: Parameters<typeof StaffingGmTab>[0]["onRebuildFromSow"];
  } = {},
) {
  return render(
    <MemoryRouter>
      <StaffingGmTab snap={buildSnap(gm)} {...opts} />
    </MemoryRouter>,
  );
}

describe("StaffingGmTab (SOW-first)", () => {
  it("renders one row per resource line, each with a provenance chip", () => {
    renderTab(buildGm());
    const usRow = screen.getByTestId("staffing-row-rl-us");
    const inRow = screen.getByTestId("staffing-row-rl-in");
    expect(within(usRow).getByTestId("provenance-chip-extracted")).toBeInTheDocument();
    expect(within(usRow).getByText(/extracted from SOW/i)).toBeInTheDocument();
    expect(within(inRow).getByTestId("provenance-chip-looked_up")).toBeInTheDocument();
    // The looked-up row also carries a warning icon.
    expect(within(inRow).getByTestId("provenance-warning")).toBeInTheDocument();
  });

  it("edit-in-place flips the row's provenance to manual via onSaveRow", async () => {
    const user = userEvent.setup();
    const saved: Array<{ id: string; patch: unknown }> = [];
    renderTab(buildGm(), {
      onSaveRow: async (id, patch) => {
        saved.push({ id, patch });
      },
    });

    await user.click(screen.getByTestId("staffing-row-edit-rl-us"));
    // Change the hours cell.
    const hoursInput = screen.getByLabelText(/Hours for row rl-us/i);
    await user.clear(hoursInput);
    await user.type(hoursInput, "500");
    await user.click(screen.getByTestId("staffing-row-save-rl-us"));

    expect(saved).toHaveLength(1);
    expect(saved[0]?.id).toBe("rl-us");
    const patch = saved[0]?.patch as {
      hours_billable: string;
      provenance_meta?: { provenance?: string; bill_rate_source?: unknown };
    };
    expect(patch.hours_billable).toBe("500");
    expect(patch.provenance_meta?.provenance).toBe("manual");
    // bill_rate_source is preserved from the pre-edit meta (even when
    // absent, the field is present so Finance can spot the flip).
    expect(patch.provenance_meta).toHaveProperty("bill_rate_source");
  });

  it("renders a FloorBar per component in the right panel", () => {
    renderTab(buildGm());
    expect(screen.getByTestId("commercial-row-us")).toBeInTheDocument();
    expect(screen.getByTestId("commercial-row-india")).toBeInTheDocument();
    expect(screen.getByTestId("commercial-row-blended")).toBeInTheDocument();
    // Each row exposes a floor bar with a fail/pass chip.
    const chips = screen.getAllByTestId("floorbar-chip");
    expect(chips.length).toBeGreaterThanOrEqual(3);
  });

  it("below-floor row renders a red fill and Fails by N pts chip", () => {
    renderTab(buildGm());
    // US component is 27.8% vs 35% floor — fails by 7.2 pts.
    const usPanel = screen.getByTestId("commercial-row-us");
    const chip = within(usPanel).getByTestId("floorbar-chip");
    expect(chip).toHaveTextContent(/Fails by 7\.2 pts/i);
    // The fill is coloured danger, not success.
    const fill = within(usPanel).getByTestId("floorbar-fill");
    expect(fill.className).toMatch(/bg-danger/);
  });

  it("shows Rebuild from SOW button when a newer sow_version exists", () => {
    const gm = buildGm({
      sow_version_id: "sv-1",
      latest_sow_version_id: "sv-2",
    });
    renderTab(gm, { onRebuildFromSow: vi.fn() });
    const btn = screen.getByTestId("staffing-rebuild-from-sow");
    expect(btn).toBeInTheDocument();
    expect(screen.getByText(/Newer SOW extraction available/i)).toBeInTheDocument();
  });

  it("never shows a blank grid — empty resource lines render an EmptyState", () => {
    const gm = buildGm({ resource_lines: [] });
    renderTab(gm);
    expect(
      screen.getByText(/Auto-staffing produced no resource lines/i),
    ).toBeInTheDocument();
  });
});
